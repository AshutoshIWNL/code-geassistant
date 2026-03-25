# =====================================
# Author: Ashutosh Mishra
# File: filewalker.py
# Created: 2025-11-21
# =====================================

'''
A custom file walker with gitignore support, binary detection, and safety filters to ensure only actual source files are processed. 
This reduces noise, improves RAG accuracy, and protects the embedding model from garbage input.
'''

import os
from pathlib import Path
from typing import List, Generator, Optional
import fnmatch
from settings import get_settings

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".mp3", ".wav", ".ogg",
    ".zip", ".gz", ".tar", ".xz",
    ".jar", ".class",
    ".so", ".dll", ".dylib",
    ".pdf"
}
DEFAULT_INTERNAL_IGNORES = [".git/", ".code_geassistant_cache/"]

def load_gitignore_patterns(workspace_path: str) -> List[str]:
    """
    Reads `.gitignore` inside the workspace if present.
    Returns a list of ignore patterns.
    """
    gitignore = Path(workspace_path) / ".gitignore"
    if not gitignore.exists():
        return []

    patterns = []
    with open(gitignore, "r") as f:
        for line in f:
            l = line.strip()
            # skip comments and empty lines
            if not l or l.startswith("#"):
                continue
            patterns.append(l)
    return patterns


def should_ignore(path: str, ignore_patterns: List[str]) -> bool:
    """
    Proper gitignore-style path ignore:
    - Pattern ending with "/" means directory
    - No fnmatch on the entire path for trailing '/'
    - Uses fnmatch ONLY for wildcard patterns
    """
    normalized = path.strip("/")

    for pattern in ignore_patterns:
        pattern = pattern.strip()

        # 1. Directory ignore rule: "dist/" means ignore anything under dist
        if pattern.endswith("/"):
            # remove trailing slash
            folder = pattern[:-1]
            if normalized == folder or normalized.startswith(folder + "/"):
                return True
            continue

        # 2. Wildcard patterns, e.g. "*.log*" or "*.ts"
        if "*" in pattern or "?" in pattern:
            if fnmatch.fnmatch(os.path.basename(path), pattern):
                return True
            continue

        # 3. Exact file match
        if os.path.basename(path) == pattern:
            return True

    return False



def is_binary_file(path: str) -> bool:
    """
    Detect binary files by extension OR null-byte.
    """
    ext = Path(path).suffix.lower()
    if ext in BINARY_EXTS:
        return True

    # Check first few KB for null bytes
    try:
        with open(path, "rb") as f:
            chunk = f.read(8000)
            if b"\0" in chunk:
                return True
    except Exception:
        return True

    return False

def walk_files(
    workspace_path: str,
    extra_ignores: Optional[List[str]] = None,
) -> Generator[dict, None, None]:
    """
    Recursively walk workspace and yield text file info.
    Yields: { path, rel_path, ext, size }
    """
    workspace_path = Path(workspace_path).resolve()
    settings = get_settings()

    gitignore_patterns = load_gitignore_patterns(workspace_path)
    all_ignores = DEFAULT_INTERNAL_IGNORES + gitignore_patterns + (extra_ignores or [])

    for root, dirs, files in os.walk(workspace_path):
        # Filter directories that should be ignored
        new_dirs = []
        for d in dirs:
            full_dir = Path(root) / d
            rel_dir = str(full_dir.relative_to(workspace_path))
            if not should_ignore(rel_dir, all_ignores):
                new_dirs.append(d)
        dirs[:] = new_dirs


        for filename in files:
            full_path = Path(root) / filename
            rel_path = str(full_path.relative_to(workspace_path))

            # Ignore patterns
            if should_ignore(rel_path, all_ignores):
                continue

            # Skip binary files
            if is_binary_file(full_path):
                continue

            # Skip huge files
            size = os.path.getsize(full_path)
            if size > settings.max_file_size_bytes:
                continue

            ext = full_path.suffix.lower()
            yield {
                "path": str(full_path),
                "rel_path": rel_path,
                "ext": ext,
                "size": size
            }
