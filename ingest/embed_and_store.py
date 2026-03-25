# =====================================
# Author: Ashutosh Mishra
# File: embed_and_store.py
# Created: 2025-11-21
# =====================================


import json
import argparse
import uuid
import math
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np

import chromadb


DEFAULT_CHROMA_DIR = "./chroma_db"


def get_sentence_transformer_class():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer


def load_chunks_jsonl(chunks_path: Path) -> List[Dict[str, Any]]:
    if not chunks_path.exists():
        raise FileNotFoundError(f"chunks.jsonl not found at: {chunks_path}")

    chunks = []
    with chunks_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except Exception:
                pass
    return chunks


def chunk_to_doc_and_meta(chunk: Dict[str, Any]):
    text = chunk.get("content", "")
    meta = {
        "rel_path": chunk.get("rel_path"),
        "start_line": chunk.get("start_line"),
        "end_line": chunk.get("end_line"),
        "n_lines": chunk.get("n_lines"),
        "est_tokens": chunk.get("est_tokens"),
        "repo": chunk.get("repo"),
        "service": chunk.get("service"),
        "language": chunk.get("language"),
        "symbol_type": chunk.get("symbol_type"),
        "symbol_name": chunk.get("symbol_name"),
    }
    return text, meta


def make_collection_name(workspace_path: Path, custom: str | None = None):
    if custom:
        return custom
    base = workspace_path.name
    return f"workspace_{base}"


def persist_embeddings(
    workspace_path: Path,
    chunks_file: Path,
    chroma_dir: str,
    collection_name: str | None,
    model_name: str,
    batch_size: int,
    encode_batch_size: int = 32,
    include_rel_paths: Optional[List[str]] = None,
    delete_rel_paths: Optional[List[str]] = None,
):
    # 1. Create Chroma persistent client (NEW API)
    client = chromadb.PersistentClient(path=chroma_dir)

    coll_name = make_collection_name(workspace_path, collection_name)
    collection = client.get_or_create_collection(
        name=coll_name,
        metadata={"hnsw:space": "cosine"}  # cosine similarity (default)
    )

    # 2. Delete stale vectors for changed/deleted files
    to_delete = sorted(set((include_rel_paths or []) + (delete_rel_paths or [])))
    for rel in to_delete:
        try:
            collection.delete(where={"rel_path": rel})
        except Exception:
            pass

    # 3. Read chunks
    chunks = load_chunks_jsonl(chunks_file)
    if include_rel_paths is not None:
        includes = set(include_rel_paths)
        chunks = [c for c in chunks if c.get("rel_path") in includes]
    if not chunks:
        print("No chunks selected for embedding. Exiting.")
        return

    print(f"Chroma DB Path   : {chroma_dir}")
    print(f"Collection Name  : {coll_name}")
    print(f"Total Chunks     : {len(chunks)}")

    # 4. Load embedding model
    print(f"Loading embedding model: {model_name}")
    model_cls = get_sentence_transformer_class()
    model = model_cls(model_name)

    total = len(chunks)
    batches = math.ceil(total / batch_size)

    processed = 0

    for i in range(batches):
        start = i * batch_size
        end = min((i + 1) * batch_size, total)
        slice_chunks = chunks[start:end]

        docs = []
        metas = []
        ids = []

        for c in slice_chunks:
            text, meta = chunk_to_doc_and_meta(c)
            unique_key = f"{workspace_path}:{meta['rel_path']}:{meta['start_line']}"
            vec_id = str(uuid.uuid5(uuid.NAMESPACE_URL, unique_key))
            docs.append(text)
            metas.append(meta)
            ids.append(vec_id)

        # 5. Embed
        emb = model.encode(docs, batch_size=encode_batch_size, show_progress_bar=False)
        emb = emb.tolist() if hasattr(emb, "tolist") else emb

        # 6. Insert/update into Chroma (idempotent for re-ingestion)
        collection.upsert(
            ids=ids,
            embeddings=emb,
            documents=docs,
            metadatas=metas,
        )

        processed += len(slice_chunks)
        print(f"Batch {i+1}/{batches} → {processed}/{total} chunks stored")

    print("\nEmbedding + storage complete!")
    print(f"Total embedded chunks: {total}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace_path")
    parser.add_argument("--collection", default=None)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--encode-batch", type=int, default=32)
    parser.add_argument("--chroma-dir", default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--model", default="all-MiniLM-L6-v2")
    parser.add_argument("--include-rel-path", action="append", default=None)
    parser.add_argument("--delete-rel-path", action="append", default=None)
    args = parser.parse_args()

    ws = Path(args.workspace_path).resolve()
    cache = ws / ".code_geassistant_cache"
    chunks_file = cache / "chunks.jsonl"

    persist_embeddings(
        ws,
        chunks_file,
        chroma_dir=args.chroma_dir,
        collection_name=args.collection,
        model_name=args.model,
        batch_size=args.batch,
        encode_batch_size=args.encode_batch,
        include_rel_paths=args.include_rel_path,
        delete_rel_paths=args.delete_rel_path,
    )


if __name__ == "__main__":
    main()
