import json
from collections import defaultdict
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse


GRAPH_VERSION = "1.0"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


def _host_to_service(host: str) -> str:
    host = (host or "").strip().lower()
    if not host:
        return "unknown_external"
    if host in {"localhost", "127.0.0.1"}:
        return "local_service"
    return host.split(".")[0]


def _normalize_http_target(target: Any) -> Tuple[str, str]:
    if not target or not isinstance(target, str):
        return "service:unknown_external", "unknown_external"
    try:
        parsed = urlparse(target)
        host = parsed.hostname or ""
        service = _host_to_service(host)
        return f"service:{service}", service
    except Exception:
        return "service:unknown_external", "unknown_external"


def build_service_graph(workspace_path: str, evidence_file: Path, graph_file: Path) -> Dict[str, Any]:
    workspace = Path(workspace_path).resolve()
    workspace_id = f"workspace_{workspace.name}"
    evidence = _read_jsonl(evidence_file)

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    route_index = defaultdict(list)

    def upsert_node(node_id: str, node_type: str, label: str, **attrs):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "label": label}
        for k, v in attrs.items():
            if v is not None:
                nodes[node_id][k] = v

    def add_edge(source: str, target: str, edge_type: str, evidence_rec: Dict[str, Any]):
        key = (source, target, edge_type)
        if key not in edges:
            edges[key] = {
                "id": f"{edge_type}:{source}->{target}",
                "source": source,
                "target": target,
                "type": edge_type,
                "evidence": [],
            }
        edges[key]["evidence"].append(
            {
                "rel_path": evidence_rec.get("rel_path"),
                "start_line": evidence_rec.get("start_line"),
                "end_line": evidence_rec.get("end_line"),
                "evidence_type": evidence_rec.get("evidence_type"),
                "confidence": evidence_rec.get("confidence"),
                "raw": evidence_rec.get("raw"),
            }
        )

    for rec in evidence:
        service = rec.get("service") or "unknown_service"
        repo = rec.get("repo")
        language = rec.get("language")
        service_node = f"service:{service}"
        upsert_node(service_node, "service", service, repo=repo, language=language)

        ev_type = rec.get("evidence_type")
        if ev_type == "route":
            method = (rec.get("method") or "ANY").upper()
            path = rec.get("path") or "unknown_path"
            endpoint_id = f"endpoint:{method}:{path}"
            upsert_node(endpoint_id, "endpoint", f"{method} {path}", method=method, path=path)
            add_edge(service_node, endpoint_id, "owns_endpoint", rec)
            route_index[f"{method} {path}"].append(service)
            continue

        if ev_type == "outbound_http":
            target_node, target_service = _normalize_http_target(rec.get("target"))
            upsert_node(target_node, "service", target_service)
            add_edge(service_node, target_node, "calls_http", rec)
            continue

        if ev_type in {"message_publish", "message_subscribe"}:
            topic = rec.get("topic") or "unknown_topic"
            topic_node = f"topic:{topic}"
            upsert_node(topic_node, "topic", topic)
            if ev_type == "message_publish":
                add_edge(service_node, topic_node, "publishes_to", rec)
            else:
                add_edge(topic_node, service_node, "consumed_by", rec)

    graph = {
        "version": GRAPH_VERSION,
        "workspace_id": workspace_id,
        "workspace_path": str(workspace),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "evidence_records": len(evidence),
            "nodes": len(nodes),
            "edges": len(edges),
        },
        "indexes": {
            "route_owners": dict(route_index),
        },
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges.values(), key=lambda e: e["id"]),
    }

    graph_file.parent.mkdir(parents=True, exist_ok=True)
    graph_file.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def load_graph(graph_file: Path) -> Dict[str, Any]:
    return json.loads(graph_file.read_text(encoding="utf-8"))


def find_neighbors(graph: Dict[str, Any], service: str, direction: str = "both") -> Dict[str, Any]:
    direction = direction.lower()
    if direction not in {"in", "out", "both"}:
        direction = "both"
    node_id = f"service:{service}"
    out = {"service": service, "direction": direction, "incoming": [], "outgoing": []}
    for edge in graph.get("edges", []):
        if edge.get("source") == node_id and direction in {"out", "both"}:
            out["outgoing"].append(edge)
        if edge.get("target") == node_id and direction in {"in", "both"}:
            out["incoming"].append(edge)
    return out


def find_endpoint_owners(graph: Dict[str, Any], method: str, path: str) -> Dict[str, Any]:
    key = f"{method.upper()} {path}"
    return {
        "method": method.upper(),
        "path": path,
        "owners": graph.get("indexes", {}).get("route_owners", {}).get(key, []),
    }


def trace_service_flow(graph: Dict[str, Any], start_service: str, max_depth: int = 2) -> Dict[str, Any]:
    node_map = {n.get("id"): n for n in graph.get("nodes", [])}
    start_node = f"service:{start_service}"
    if start_node not in node_map:
        return {
            "start_service": start_service,
            "max_depth": max_depth,
            "steps": [],
            "visited_services": [],
            "missing_links": [f"service '{start_service}' not found in graph"],
            "confidence": "low",
        }

    adjacency = defaultdict(list)
    for edge in graph.get("edges", []):
        adjacency[edge.get("source")].append(edge)

    queue = deque([(start_node, 0)])
    seen = {start_node}
    steps: List[Dict[str, Any]] = []
    missing_links: List[str] = []
    visited_services = {start_service}

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue

        outgoing = adjacency.get(current, [])
        if not outgoing and current.startswith("service:"):
            missing_links.append(f"no outgoing edges from {current.split(':', 1)[1]}")

        for edge in outgoing:
            target = edge.get("target")
            if not target:
                continue
            source_label = node_map.get(current, {}).get("label", current)
            target_label = node_map.get(target, {}).get("label", target)
            steps.append(
                {
                    "depth": depth + 1,
                    "edge_type": edge.get("type"),
                    "source": source_label,
                    "target": target_label,
                    "source_node_id": current,
                    "target_node_id": target,
                    "evidence_count": len(edge.get("evidence", [])),
                }
            )

            if target.startswith("service:"):
                visited_services.add(target.split(":", 1)[1])

            if target not in seen:
                seen.add(target)
                queue.append((target, depth + 1))

    confidence = "low"
    if steps:
        confidence = "medium"
        if any(s.get("edge_type") in {"calls_http", "owns_endpoint"} for s in steps):
            confidence = "high"

    return {
        "start_service": start_service,
        "max_depth": max_depth,
        "steps": steps,
        "visited_services": sorted(visited_services),
        "missing_links": missing_links,
        "confidence": confidence,
    }
