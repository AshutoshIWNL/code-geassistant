# =====================================
# Author: Ashutosh Mishra
# File: ingest_worker.py
# Created: 2025-11-21
# =====================================

import json
import math
from pathlib import Path
from typing import List, Dict, Any

from .filewalker import walk_files
from .chunker import chunk_file

# Can be tuned later (or configurable)
DEFAULT_CHUNK_LINES = 80
DEFAULT_OVERLAP_LINES = 20

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
    extra_ignores: List[str] = [],
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

    # Clear previous chunks if any
    if out_file.exists():
        out_file.unlink()

    files = list(walk_files(workspace_path, extra_ignores=extra_ignores))
    total_files = len(files)
    job_state["status"] = "running"
    job_state["total_files"] = total_files
    job_state["files_processed"] = 0
    job_state["total_chunks"] = 0

    # Open file and stream chunks
    with out_file.open("a", encoding="utf-8") as fh:
        for idx, file_info in enumerate(files):
            # update progress
            job_state["current_file"] = file_info["rel_path"]
            job_state["files_processed"] = idx

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
                }
                fh.write(json.dumps(serialized, ensure_ascii=False) + "\n")
                produced += 1
                job_state["total_chunks"] = job_state.get("total_chunks", 0) + 1

            job_state["last_file_count_chunks"] = produced
            # lightweight progress percentage
            job_state["progress"] = math.floor(((idx + 1) / total_files) * 100) if total_files else 100

    job_state["status"] = "done"
    job_state["files_processed"] = total_files
    job_state["progress"] = 100
    return {
        "workspace": workspace_path,
        "total_files": total_files,
        "total_chunks": job_state["total_chunks"],
        "chunks_file": str(out_file),
    }