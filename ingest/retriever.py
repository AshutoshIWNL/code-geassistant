# =====================================
# Author: Ashutosh Mishra
# File: retriever.py
# Created: 2025-11-21
# =====================================

from pathlib import Path
from typing import List, Dict, Any
import chromadb
from sentence_transformers import SentenceTransformer


DEFAULT_CHROMA_DIR = "./chroma_db"
DEFAULT_MODEL = "all-MiniLM-L6-v2"


class CodeRetriever:
    """
    Handles:
      - loading embedding model
      - connecting to Chroma persistent DB
      - querying for semantically related chunks
      - building context prompts
    """

    def __init__(
        self,
        chroma_dir: str = DEFAULT_CHROMA_DIR,
        model_name: str = DEFAULT_MODEL,
    ):
        self.chroma_dir = chroma_dir
        self.client = chromadb.PersistentClient(path=chroma_dir)
        self.model = SentenceTransformer(model_name, local_files_only=True)

    def get_collection(self, name: str):
        """Load or create collection."""
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )

    def embed_text(self, text: str):
        """Return embedding vector (as Python list)."""
        vec = self.model.encode(text)
        return vec.tolist()

    def retrieve(
        self,
        collection_name: str,
        query: str,
        k: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Search for the top-k most relevant chunks for a query.
        Returns list of dicts with {text, metadata, score}.
        """
        coll = self.get_collection(collection_name)
        q_emb = self.embed_text(query)

        # Chroma 0.5+ `query` API:
        # returns: { "ids": [], "distances": [], "documents": [], "metadatas": [] }
        results = coll.query(
            query_embeddings=[q_emb],
            n_results=k,
            include=["documents", "metadatas", "distances"]
        )

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        out = []
        for doc, meta, dist in zip(docs, metas, distances):
            out.append({
                "content": doc,
                "metadata": meta,
                "score": 1 - dist  # convert distance → similarity for readability
            })

        # Sort by similarity (higher is better)
        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    def build_context_prompt(
        self,
        retrieved_chunks: List[Dict[str, Any]],
        question: str
    ) -> str:
        """
        Build a nice compact prompt for the LLM with all retrieved chunks.
        """
        parts = ["You are a code assistant with full context."]

        for i, item in enumerate(retrieved_chunks, start=1):
            meta = item["metadata"]
            parts.append(
                f"\n----- Chunk {i} | {meta['rel_path']} "
                f"(lines {meta['start_line']}-{meta['end_line']}) -----\n"
                f"{item['content']}\n"
            )

        parts.append("\n----- Question -----\n" + question)

        return "\n".join(parts)