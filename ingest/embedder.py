# =====================================
# Author: Ashutosh Mishra
# File: embedder.py
# Created: 2025-11-29
# =====================================

from pathlib import Path
from typing import Optional, List
from ingest.embed_and_store import persist_embeddings
from settings import get_settings


def embed_workspace(
    workspace_path: str,
    chroma_dir: str = "./chroma_db",
    changed_or_new_rel_paths: Optional[List[str]] = None,
    deleted_rel_paths: Optional[List[str]] = None,
):
    """
    Called AFTER chunking. Automatically finds chunks.jsonl
    and pushes embeddings to Chroma.
    """
    settings = get_settings()
    ws = Path(workspace_path).resolve()
    chunks_file = ws / ".code_geassistant_cache" / "chunks.jsonl"

    persist_embeddings(
        workspace_path=ws,
        chunks_file=chunks_file,
        chroma_dir=chroma_dir,
        collection_name=None,
        model_name=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
        encode_batch_size=settings.embedding_encode_batch_size,
        include_rel_paths=changed_or_new_rel_paths,
        delete_rel_paths=deleted_rel_paths,
    )
