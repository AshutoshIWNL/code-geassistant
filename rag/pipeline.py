# =====================================
# Author: Ashutosh Mishra
# File: pipeline.py
# Created: 2025-11-21
# =====================================

# Combines Retriever + LLM into a single function: answer_query()

from ingest.retriever import CodeRetriever
from llm.llm_adapter import LLMAdapter


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

    def answer_query(self, collection_name: str, question: str) -> dict:
        """
        1. Retrieve top-k context chunks
        2. Build full prompt
        3. Generate answer using LLMAdapter
        4. Return answer + source metadata
        """
        # 1. retrieve chunks
        chunks = self.retriever.retrieve(collection_name, question, k=self.top_k)

        # 2. build prompt
        prompt = self.retriever.build_context_prompt(chunks, question)

        # 3. call LLM
        answer = self.llm.generate(prompt)

        # 4. return answer and references
        sources = [
            {
                "rel_path": c["metadata"]["rel_path"],
                "start_line": c["metadata"]["start_line"],
                "end_line": c["metadata"]["end_line"],
                "score": c["score"],
            }
            for c in chunks
        ]

        return {
            "answer": answer,
            "sources": sources
        }