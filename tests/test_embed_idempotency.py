import json
from pathlib import Path

from ingest import embed_and_store


class _FakeCollection:
    def __init__(self):
        self.upsert_calls = 0
        self.delete_calls = 0

    def upsert(self, ids, embeddings, documents, metadatas):
        self.upsert_calls += 1
        assert len(ids) == len(embeddings) == len(documents) == len(metadatas)

    def delete(self, where=None):
        self.delete_calls += 1


class _FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name, metadata=None):
        return self.collection


class _FakeModel:
    def __init__(self, name):
        self.name = name

    def encode(self, docs, batch_size=32, show_progress_bar=False):
        return [[0.0, 1.0] for _ in docs]


def test_persist_embeddings_reingest_is_idempotent(monkeypatch, tmp_path: Path):
    ws = tmp_path / "repo"
    ws.mkdir()
    cache = ws / ".code_geassistant_cache"
    cache.mkdir()
    chunks_file = cache / "chunks.jsonl"
    chunk = {
        "rel_path": "src/app.py",
        "start_line": 1,
        "end_line": 3,
        "n_lines": 3,
        "est_tokens": 5,
        "content": "def x():\n    return 1\n",
    }
    chunks_file.write_text(json.dumps(chunk) + "\n", encoding="utf-8")

    collection = _FakeCollection()
    monkeypatch.setattr(embed_and_store, "get_sentence_transformer_class", lambda: _FakeModel)
    monkeypatch.setattr(
        embed_and_store.chromadb,
        "PersistentClient",
        lambda path: _FakeClient(collection),
    )

    # First ingest
    embed_and_store.persist_embeddings(
        workspace_path=ws,
        chunks_file=chunks_file,
        chroma_dir=str(tmp_path / "chroma"),
        collection_name=None,
        model_name="fake-embed",
        batch_size=64,
        encode_batch_size=16,
    )

    # Re-ingest same content should succeed (upsert-based)
    embed_and_store.persist_embeddings(
        workspace_path=ws,
        chunks_file=chunks_file,
        chroma_dir=str(tmp_path / "chroma"),
        collection_name=None,
        model_name="fake-embed",
        batch_size=64,
        encode_batch_size=16,
    )

    assert collection.upsert_calls == 2


def test_persist_embeddings_supports_include_and_delete(monkeypatch, tmp_path: Path):
    ws = tmp_path / "repo"
    ws.mkdir()
    cache = ws / ".code_geassistant_cache"
    cache.mkdir()
    chunks_file = cache / "chunks.jsonl"
    chunk_a = {
        "rel_path": "a.py",
        "start_line": 1,
        "end_line": 2,
        "n_lines": 2,
        "est_tokens": 4,
        "content": "print('a')\n",
    }
    chunk_b = {
        "rel_path": "b.py",
        "start_line": 1,
        "end_line": 2,
        "n_lines": 2,
        "est_tokens": 4,
        "content": "print('b')\n",
    }
    chunks_file.write_text(
        json.dumps(chunk_a) + "\n" + json.dumps(chunk_b) + "\n",
        encoding="utf-8",
    )

    collection = _FakeCollection()
    monkeypatch.setattr(embed_and_store, "get_sentence_transformer_class", lambda: _FakeModel)
    monkeypatch.setattr(
        embed_and_store.chromadb,
        "PersistentClient",
        lambda path: _FakeClient(collection),
    )

    embed_and_store.persist_embeddings(
        workspace_path=ws,
        chunks_file=chunks_file,
        chroma_dir=str(tmp_path / "chroma"),
        collection_name=None,
        model_name="fake-embed",
        batch_size=64,
        encode_batch_size=16,
        include_rel_paths=["a.py"],
        delete_rel_paths=["old.py"],
    )

    assert collection.delete_calls == 2
    assert collection.upsert_calls == 1
