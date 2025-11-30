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
from typing import Dict, Any, List

import numpy as np
from sentence_transformers import SentenceTransformer

import chromadb


DEFAULT_CHROMA_DIR = "./chroma_db"


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
):
    # 1. Read chunks
    chunks = load_chunks_jsonl(chunks_file)
    if not chunks:
        print("No chunks found. Exiting.")
        return

    # 2. Create Chroma persistent client (NEW API)
    client = chromadb.PersistentClient(path=chroma_dir)

    coll_name = make_collection_name(workspace_path, collection_name)
    collection = client.get_or_create_collection(
        name=coll_name,
        metadata={"hnsw:space": "cosine"}  # cosine similarity (default)
    )

    print(f"Chroma DB Path   : {chroma_dir}")
    print(f"Collection Name  : {coll_name}")
    print(f"Total Chunks     : {len(chunks)}")

    # 3. Load embedding model
    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

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

        # 4. Embed
        emb = model.encode(docs, batch_size=32, show_progress_bar=False)
        emb = emb.tolist()

        # 5. Insert into Chroma (NEW API)
        collection.add(
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
    parser.add_argument("--chroma-dir", default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--model", default="all-MiniLM-L6-v2")
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
    )


if __name__ == "__main__":
    main()
