import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.llm.adapter import LLMConfig, StubAdapter, build_adapter
from app.main import app

client = TestClient(app)
FROZEN = Path(__file__).parent.parent / "openapi.json"


def test_openapi_file_is_frozen():
    assert json.loads(FROZEN.read_text()) == app.openapi(), (
        "API contract changed: regenerate with `python -m app.export_openapi > openapi.json`"
    )


def test_mock_endpoints_return_openapi_examples():
    assert client.post("/api/v1/auth/login", json={"email": "a@b.c", "password": "x"}).json()[
        "token_type"
    ] == "bearer"
    assert client.get("/api/v1/problems", params={"course_id": 1}).json()["problems"][0]["id"] == 1
    assert client.post("/api/v1/submissions", json={"problem_id": 1, "code": "x"}).json()[
        "submission_id"
    ] == 412
    assert client.post("/api/v1/diagnostic/start").json()["max_items"] == 10
    assert client.post(
        "/api/v1/diagnostic/answer", json={"session_id": "s", "problem_id": 1, "answer": "a"}
    ).json()["done"] is False
    assert client.post("/api/v1/chat", json={"message": "hi"}).json()["route"] == "general"


def test_validation_error_uses_the_single_error_shape():
    response = client.post("/api/v1/chat", json={})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_unknown_route_uses_the_single_error_shape():
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_request_id_is_echoed_and_logged(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}
    assert any(r.fields["path"] == "/api/v1/health" for r in caplog.records)


def test_llm_adapter_returns_canned_reply_from_environment_config(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT_S", "7")
    get_settings.cache_clear()
    adapter = build_adapter(get_settings())
    get_settings.cache_clear()
    assert isinstance(adapter, StubAdapter)
    assert adapter.config == LLMConfig("stub", "test-model", 7.0, 1, 0.1)
    assert adapter.complete("system", "user") == StubAdapter.reply
