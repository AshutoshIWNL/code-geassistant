# =====================================
# Author: Ashutosh Mishra
# File: chunker.py
# Created: 2025-11-21
# =====================================

'''
A custom chunker that produces metadata-rich slices optimized for RAG retrieval. 
Instead of embedding entire files (which pollutes search and overloads LLM context), each file becomes 20–40 precise embeddings with local semantic boundaries.
'''

from pathlib import Path
from typing import Dict, Any, Generator, List


def read_file_safely(path: str) -> List[str]:
    """Read file as UTF-8, fallback to latin-1. Return list of lines (no trailing newlines)."""
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        try:
            return p.read_text(encoding="latin-1").splitlines()
        except Exception:
            return []


def estimate_tokens_for_text(text: str) -> int:
    """
    Rough token estimate: ~1 token per 4 characters for code/text.
    Not exact — used to reason about chunk size.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_tokens(lines: List[str]) -> int:
    return sum(estimate_tokens_for_text(line) for line in lines)


def chunk_file(
    file_info: Dict[str, Any],
    chunk_size_lines: int = 80,
    overlap_lines: int = 20,
) -> Generator[Dict[str, Any], None, None]:
    """
    Yield chunks for a file.
    file_info must include: "path" (absolute path), "rel_path"
    Chunk shape:
      {
        "rel_path": str,
        "start_line": int,  # 1-indexed
        "end_line": int,
        "content": str,
        "n_lines": int,
        "est_tokens": int
      }
    """
    path = file_info.get("path")
    if not path:
        return

    lines = read_file_safely(path)
    if not lines:
        return

    total_lines = len(lines)
    i = 0
    while i < total_lines:
        start = i
        end = min(i + chunk_size_lines, total_lines)

        chunk_lines = lines[start:end]
        content = "\n".join(chunk_lines)
        est_tokens = estimate_tokens(chunk_lines)

        yield {
            "rel_path": file_info.get("rel_path"),
            "start_line": start + 1,
            "end_line": end,
            "content": content,
            "n_lines": len(chunk_lines),
            "est_tokens": est_tokens,
        }

        if end == total_lines:
            break

        i = i + chunk_size_lines - overlap_lines
        if i < 0:
            i = 0