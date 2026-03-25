# =====================================
# Author: Ashutosh Mishra
# File: ingest_worker.py
# Created: 2025-11-21
# =====================================

import json
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

from .filewalker import walk_files
from .chunker import chunk_file
from .metadata import build_file_metadata
from .evidence import extract_evidence_for_file
from .graph_builder import build_service_graph
from .incremental import load_manifest, save_manifest, make_fingerprint
from settings import get_settings

_settings = get_settings()
DEFAULT_CHUNK_LINES = _settings.chunk_lines
DEFAULT_OVERLAP_LINES = _settings.overlap_lines

def ensure_workspace_cache(workspace_path: str) -> Path:
    """
    Create a workspace cache directory to store chunk files and metadata.
    Returns Path to cache dir.
    """
    ws = Path(workspace_path).resolve()
    cache = ws / ".code_geassistant_cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def ingest_workspace_to_chunks(
    workspace_path: str,
    job_state: Dict[str, Any],
    extra_ignores: Optional[List[str]] = None,
    chunk_lines: int = DEFAULT_CHUNK_LINES,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> Dict[str, Any]:
    """
    Walk workspace, chunk files, write chunks to workspace cache (JSONL).
    Updates job_state dict with progress keys: status, total_files, files_processed, total_chunks.
    Returns summary dict.
    """
    cache = ensure_workspace_cache(workspace_path)
    out_file = cache / "chunks.jsonl"
    evidence_file = cache / "evidence.jsonl"
    graph_file = cache / "service_graph.json"

    files = list(walk_files(workspace_path, extra_ignores=extra_ignores or []))
    total_files = len(files)
    files_by_rel = {f["rel_path"]: f for f in files}
    previous_manifest = load_manifest(cache)
    prev_files_map = previous_manifest.get("files", {})
    current_fingerprints = {rel: make_fingerprint(info) for rel, info in files_by_rel.items()}

    new_files = sorted([rel for rel in files_by_rel if rel not in prev_files_map])
    changed_files = sorted([
        rel for rel in files_by_rel
        if rel in prev_files_map and prev_files_map.get(rel) != current_fingerprints.get(rel)
    ])
    unchanged_files = sorted([
        rel for rel in files_by_rel
        if rel in prev_files_map and prev_files_map.get(rel) == current_fingerprints.get(rel)
    ])
    deleted_files = sorted([rel for rel in prev_files_map if rel not in files_by_rel])

    changed_or_new = set(new_files + changed_files)

    job_state["status"] = "running"
    job_state["total_files"] = total_files
    job_state["files_processed"] = 0
    job_state["total_chunks"] = 0
    job_state["total_evidence"] = 0
    job_state["graph_nodes"] = 0
    job_state["graph_edges"] = 0
    job_state["new_files"] = len(new_files)
    job_state["changed_files"] = len(changed_files)
    job_state["deleted_files"] = len(deleted_files)
    job_state["unchanged_files"] = len(unchanged_files)

    prev_chunks_by_file = {}
    prev_evidence_by_file = {}
    if out_file.exists():
        with out_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except Exception:
                    continue
                rel = rec.get("rel_path")
                if rel:
                    prev_chunks_by_file.setdefault(rel, []).append(rec)
    if evidence_file.exists():
        with evidence_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except Exception:
                    continue
                rel = rec.get("rel_path")
                if rel:
                    prev_evidence_by_file.setdefault(rel, []).append(rec)

    temp_chunks_file = cache / "chunks.jsonl.tmp"
    temp_evidence_file = cache / "evidence.jsonl.tmp"
    if temp_chunks_file.exists():
        temp_chunks_file.unlink()
    if temp_evidence_file.exists():
        temp_evidence_file.unlink()

    # Open files and stream chunks/evidence (reuse unchanged cache content)
    with temp_chunks_file.open("a", encoding="utf-8") as fh_chunks, temp_evidence_file.open("a", encoding="utf-8") as fh_evidence:
        for idx, file_info in enumerate(files):
            # update progress
            job_state["current_file"] = file_info["rel_path"]
            job_state["files_processed"] = idx + 1
            rel_path = file_info["rel_path"]

            if rel_path not in changed_or_new:
                reused_chunks = prev_chunks_by_file.get(rel_path, [])
                reused_ev = prev_evidence_by_file.get(rel_path, [])
                for rec in reused_chunks:
                    fh_chunks.write(json.dumps(rec, ensure_ascii=False) + "\n")
                for rec in reused_ev:
                    fh_evidence.write(json.dumps(rec, ensure_ascii=False) + "\n")
                job_state["total_chunks"] = job_state.get("total_chunks", 0) + len(reused_chunks)
                job_state["total_evidence"] = job_state.get("total_evidence", 0) + len(reused_ev)
                job_state["last_file_count_chunks"] = len(reused_chunks)
                job_state["last_file_count_evidence"] = len(reused_ev)
                job_state["progress"] = math.floor(((idx + 1) / total_files) * 100) if total_files else 100
                continue

            file_meta = build_file_metadata(workspace_path, file_info)

            evidence_records = extract_evidence_for_file(workspace_path, file_info)
            for ev in evidence_records:
                fh_evidence.write(json.dumps(ev, ensure_ascii=False) + "\n")
            job_state["last_file_count_evidence"] = len(evidence_records)
            job_state["total_evidence"] = job_state.get("total_evidence", 0) + len(evidence_records)

            # produce chunks
            produced = 0
            for chunk in chunk_file(file_info, chunk_size_lines=chunk_lines, overlap_lines=overlap_lines):
                # minimal metadata written on disk (avoid huge memory)
                serialized = {
                    "rel_path": chunk["rel_path"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "n_lines": chunk["n_lines"],
                    "est_tokens": chunk["est_tokens"],
                    "content": chunk["content"],
                    "repo": file_meta["repo"],
                    "service": file_meta["service"],
                    "language": file_meta["language"],
                    "symbol_type": file_meta["symbol_type"],
                    "symbol_name": file_meta["symbol_name"],
                }
                fh_chunks.write(json.dumps(serialized, ensure_ascii=False) + "\n")
                produced += 1
                job_state["total_chunks"] = job_state.get("total_chunks", 0) + 1

            job_state["last_file_count_chunks"] = produced
            # lightweight progress percentage
            job_state["progress"] = math.floor(((idx + 1) / total_files) * 100) if total_files else 100

    temp_chunks_file.replace(out_file)
    temp_evidence_file.replace(evidence_file)

    graph = build_service_graph(workspace_path, evidence_file=evidence_file, graph_file=graph_file)
    job_state["graph_nodes"] = graph.get("stats", {}).get("nodes", 0)
    job_state["graph_edges"] = graph.get("stats", {}).get("edges", 0)
    job_state["graph_file"] = str(graph_file)

    save_manifest(cache, current_fingerprints)

    job_state["status"] = "done"
    job_state["files_processed"] = total_files
    job_state["progress"] = 100
    return {
        "workspace": workspace_path,
        "total_files": total_files,
        "total_chunks": job_state["total_chunks"],
        "total_evidence": job_state["total_evidence"],
        "graph_nodes": job_state["graph_nodes"],
        "graph_edges": job_state["graph_edges"],
        "new_files": len(new_files),
        "changed_files": len(changed_files),
        "deleted_files": len(deleted_files),
        "unchanged_files": len(unchanged_files),
        "changed_or_new_rel_paths": sorted(list(changed_or_new)),
        "deleted_rel_paths": deleted_files,
        "chunks_file": str(out_file),
        "evidence_file": str(evidence_file),
        "graph_file": str(graph_file),
    }
