# =====================================
# Author: Ashutosh Mishra
# File: pipeline.py
# Created: 2025-11-21
# =====================================

# Combines Retriever + LLM into a single function: answer_query()

from ingest.retriever import CodeRetriever
from llm.llm_adapter import LLMAdapter
from typing import Optional, Dict, Any


class RAGPipeline:
    def __init__(
        self,
        chroma_dir="./chroma_db",
        model_provider="ollama",
        model_name="llama3:8b",
        top_k=6,
    ):
        self.retriever = CodeRetriever(chroma_dir=chroma_dir)
        self.llm = LLMAdapter(provider=model_provider, model=model_name)
        self.top_k = top_k

    def answer_query(
        self,
        collection_name: str,
        question: str,
        model_name: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        1. Retrieve top-k context chunks
        2. Build full prompt
        3. Generate answer using LLMAdapter
        4. Return answer + source metadata
        """
        # 1. retrieve chunks
        chunks = self.retriever.retrieve(
            collection_name,
            question,
            k=self.top_k,
            metadata_filter=metadata_filter,
        )

        # 2. build prompt
        prompt = self.retriever.build_context_prompt(chunks, question)

        # 3. call LLM
        llm = self.llm
        if model_name and model_name != self.llm.model:
            llm = LLMAdapter(provider=llm.provider, model=model_name)

        answer = llm.generate(prompt)

        # 4. return answer and references
        sources = [
            {
                "rel_path": c["metadata"]["rel_path"],
                "start_line": c["metadata"]["start_line"],
                "end_line": c["metadata"]["end_line"],
                "score": c["score"],
                "repo": c["metadata"].get("repo"),
                "service": c["metadata"].get("service"),
                "language": c["metadata"].get("language"),
                "symbol_type": c["metadata"].get("symbol_type"),
                "symbol_name": c["metadata"].get("symbol_name"),
            }
            for c in chunks
        ]

        return {
            "answer": answer,
            "sources": sources,
            "model_used": llm.model,
        }
