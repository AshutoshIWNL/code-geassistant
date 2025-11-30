# =====================================
# Author: Ashutosh Mishra
# File: llm_adapter.py
# Created: 2025-11-21
# =====================================

# Unified LLM interface for:
#   - Ollama (http://localhost:11434)
#   - llama.cpp (local .gguf models)
#
# Usage:
#   llm = LLMAdapter(provider="ollama", model="llama3:8b")
#   answer = llm.generate("What is 2+2?")

from typing import Optional, Generator

# Optional imports — only load what backend is used
try:
    import ollama
except ImportError:
    ollama = None

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None


class LLMAdapter:
    def __init__(
        self,
        provider: str = "ollama",  # "ollama" or "llamacpp"
        model: str = "deepseek-coder:1.3b",  # ollama model OR path to llama.cpp .gguf
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ):
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

        if provider == "ollama":
            if ollama is None:
                raise ImportError("ollama python package not installed: pip install ollama")
            # nothing else to initialize

        elif provider == "llamacpp":
            if Llama is None:
                raise ImportError("llama_cpp package not installed: pip install llama-cpp-python")
            print(f"Loading llama.cpp model: {model}")
            self.llm = Llama(
                model_path=model,
                n_ctx=8192,
                n_threads=8,
                verbose=False
            )

        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    # ------------------------------------------------------
    # Non-streaming generate()
    # ------------------------------------------------------
    def generate(self, prompt: str) -> str:
        """Return the full string response (no streaming)."""

        if self.provider == "ollama":
            resp = ollama.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "num_predict": self.max_tokens
                }
            )
            return resp["response"]

        elif self.provider == "llamacpp":
            out = self.llm(
                prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                echo=False,
            )
            return out["choices"][0]["text"]

    # ------------------------------------------------------
    # Streaming generate()
    # ------------------------------------------------------
    def stream(self, prompt: str) -> Generator[str, None, None]:
        """Yield tokens/strings as they are generated."""

        if self.provider == "ollama":
            stream = ollama.generate(
                model=self.model,
                prompt=prompt,
                stream=True,
                options={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "num_predict": self.max_tokens
                }
            )
            for part in stream:
                yield part["response"]

        elif self.provider == "llamacpp":
            for out in self.llm(
                prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                echo=False,
                stream=True,
            ):
                if "choices" in out:
                    yield out["choices"][0]["text"]
