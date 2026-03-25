import os
from dataclasses import dataclass
from functools import lru_cache


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    chroma_dir: str
    model_provider: str
    default_llm_model: str
    top_k: int
    embedding_model: str
    embedding_batch_size: int
    embedding_encode_batch_size: int
    chunk_lines: int
    overlap_lines: int
    max_file_size_bytes: int
    llm_max_tokens: int
    llm_temperature: float
    llm_top_p: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        chroma_dir=os.getenv("CGA_CHROMA_DIR", "./chroma_db"),
        model_provider=os.getenv("CGA_MODEL_PROVIDER", "ollama"),
        default_llm_model=os.getenv("CGA_DEFAULT_LLM_MODEL", "deepseek-coder:1.3b"),
        top_k=_get_int("CGA_TOP_K", 6),
        embedding_model=os.getenv("CGA_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        embedding_batch_size=_get_int("CGA_EMBEDDING_BATCH_SIZE", 64),
        embedding_encode_batch_size=_get_int("CGA_EMBEDDING_ENCODE_BATCH_SIZE", 32),
        chunk_lines=_get_int("CGA_CHUNK_LINES", 80),
        overlap_lines=_get_int("CGA_OVERLAP_LINES", 20),
        max_file_size_bytes=_get_int("CGA_MAX_FILE_SIZE_BYTES", 2 * 1024 * 1024),
        llm_max_tokens=_get_int("CGA_LLM_MAX_TOKENS", 512),
        llm_temperature=_get_float("CGA_LLM_TEMPERATURE", 0.0),
        llm_top_p=_get_float("CGA_LLM_TOP_P", 1.0),
    )
