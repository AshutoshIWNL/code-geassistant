# =====================================
# Author: Ashutosh Mishra
# File: embedder.py
# Created: 2025-11-29
# =====================================

from pathlib import Path
from ingest.embed_and_store import persist_embeddings


def embed_workspace(workspace_path: str, chroma_dir: str = "./chroma_db"):
    """
    Called AFTER chunking. Automatically finds chunks.jsonl
    and pushes embeddings to Chroma.
    """
    ws = Path(workspace_path).resolve()
    chunks_file = ws / ".code_geassistant_cache" / "chunks.jsonl"

    persist_embeddings(
        workspace_path=ws,
        chunks_file=chunks_file,
        chroma_dir=chroma_dir,
        collection_name=None,
        model_name="all-MiniLM-L6-v2",
        batch_size=64
    )
