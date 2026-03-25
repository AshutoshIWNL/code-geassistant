from fastapi.testclient import TestClient

import main


class _FakeCollection:
    def __init__(self, name: str):
        self.name = name


class _FakeChromaClient:
    def list_collections(self):
        return [_FakeCollection("workspace_demo")]


class _FakePipeline:
    def answer_query(self, collection_name: str, question: str, model_name=None, metadata_filter=None):
        return {
            "answer": f"echo:{question}",
            "sources": [
                {
                    "rel_path": "src/app.py",
                    "start_line": 1,
                    "end_line": 10,
                    "score": 0.9,
                }
            ],
            "model_used": model_name or "fake-default",
        }


def test_query_response_shape(monkeypatch):
    monkeypatch.setattr(main, "get_pipeline", lambda: _FakePipeline())
    monkeypatch.setattr(
        main.chromadb,
        "PersistentClient",
        lambda path: _FakeChromaClient(),
    )

    client = TestClient(main.app)
    resp = client.post(
        "/query",
        json={
            "workspace_id": "workspace_demo",
            "question": "where is auth?",
            "model": "fake-llm",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) >= {"answer", "sources", "model_used", "workspace"}
    assert body["workspace"] == "workspace_demo"
    assert body["model_used"] == "fake-llm"
    assert isinstance(body["sources"], list)
    assert body["sources"][0]["rel_path"] == "src/app.py"


def test_query_metadata_filters_forwarded(monkeypatch):
    captured = {}

    class _CapturePipeline:
        def answer_query(self, collection_name: str, question: str, model_name=None, metadata_filter=None):
            captured["collection_name"] = collection_name
            captured["question"] = question
            captured["model_name"] = model_name
            captured["metadata_filter"] = metadata_filter
            return {"answer": "ok", "sources": [], "model_used": model_name or "x"}

    monkeypatch.setattr(main, "get_pipeline", lambda: _CapturePipeline())
    monkeypatch.setattr(
        main.chromadb,
        "PersistentClient",
        lambda path: _FakeChromaClient(),
    )

    client = TestClient(main.app)
    resp = client.post(
        "/query",
        json={
            "workspace_id": "workspace_demo",
            "question": "find endpoint",
            "repo": "demo-repo",
            "service": "orders",
            "language": "java",
            "symbol_type": "endpoint_handler",
        },
    )

    assert resp.status_code == 200
    assert captured["collection_name"] == "workspace_demo"
    assert captured["question"] == "find endpoint"
    assert captured["metadata_filter"] == {
        "repo": "demo-repo",
        "service": "orders",
        "language": "java",
        "symbol_type": "endpoint_handler",
    }


def test_query_mode_owner_of_endpoint(monkeypatch):
    fake_graph = {
        "indexes": {"route_owners": {"GET /orders": ["orders"]}},
        "edges": [],
        "nodes": [],
    }
    monkeypatch.setattr(
        main.chromadb,
        "PersistentClient",
        lambda path: _FakeChromaClient(),
    )
    monkeypatch.setattr(main, "_resolve_graph_file", lambda workspace_id: None)
    monkeypatch.setattr(main, "load_graph", lambda _: fake_graph)

    client = TestClient(main.app)
    resp = client.post(
        "/query",
        json={
            "workspace_id": "workspace_demo",
            "query_mode": "owner_of_endpoint",
            "method": "GET",
            "path": "/orders",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_mode"] == "owner_of_endpoint"
    assert body["owners"]["owners"] == ["orders"]


def test_query_mode_trace_flow(monkeypatch):
    fake_graph = {
        "nodes": [
            {"id": "service:orders", "label": "orders"},
            {"id": "service:payments", "label": "payments"},
        ],
        "edges": [
            {
                "id": "calls_http:service:orders->service:payments",
                "source": "service:orders",
                "target": "service:payments",
                "type": "calls_http",
                "evidence": [{"rel_path": "a.py", "start_line": 1, "end_line": 1}],
            }
        ],
        "indexes": {"route_owners": {}},
    }
    monkeypatch.setattr(
        main.chromadb,
        "PersistentClient",
        lambda path: _FakeChromaClient(),
    )
    monkeypatch.setattr(main, "_resolve_graph_file", lambda workspace_id: None)
    monkeypatch.setattr(main, "load_graph", lambda _: fake_graph)

    client = TestClient(main.app)
    resp = client.post(
        "/query",
        json={
            "workspace_id": "workspace_demo",
            "query_mode": "trace_flow",
            "service": "orders",
            "trace_depth": 2,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_mode"] == "trace_flow"
    assert body["flow"]["start_service"] == "orders"
    assert len(body["flow"]["steps"]) >= 1
