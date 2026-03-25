import json
from pathlib import Path

from ingest.graph_builder import build_service_graph, find_endpoint_owners, find_neighbors


def test_build_service_graph_from_evidence(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    cache = workspace / ".code_geassistant_cache"
    cache.mkdir()

    evidence_file = cache / "evidence.jsonl"
    graph_file = cache / "service_graph.json"

    records = [
        {
            "evidence_type": "route",
            "service": "orders",
            "repo": "repo",
            "language": "javascript",
            "method": "GET",
            "path": "/orders",
            "rel_path": "services/orders/routes.js",
            "start_line": 10,
            "end_line": 10,
            "confidence": "medium",
            "raw": 'app.get("/orders", handler)',
        },
        {
            "evidence_type": "outbound_http",
            "service": "orders",
            "target": "https://payments.internal/api",
            "rel_path": "services/orders/client.js",
            "start_line": 22,
            "end_line": 22,
            "confidence": "low",
            "raw": 'fetch("https://payments.internal/api")',
        },
    ]
    evidence_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    graph = build_service_graph(str(workspace), evidence_file, graph_file)
    assert graph_file.exists()
    assert graph["stats"]["nodes"] >= 3
    assert graph["stats"]["edges"] >= 2

    owners = find_endpoint_owners(graph, "GET", "/orders")
    assert owners["owners"] == ["orders"]

    neighbors = find_neighbors(graph, "orders", direction="out")
    assert len(neighbors["outgoing"]) >= 1
