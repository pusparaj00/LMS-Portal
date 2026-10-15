"""TR-A-01: a write is committed before its reply leaves, so the next request always sees it."""
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import Conn

API = "/api/v1"


def test_the_commit_happens_before_the_response_is_sent(monkeypatch):
    events = []
    app = FastAPI()

    class FakeConn:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    class FakeEngine:
        def connect(self):
            return self

        def __enter__(self):
            return FakeConn()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("app.auth.get_engine", lambda: FakeEngine())

    @app.post("/write")
    def write(conn: Conn):
        events.append("handler")
        return {"ok": True}

    @app.middleware("http")
    async def mark_response(request, call_next):
        response = await call_next(request)
        events.append("response")
        return response

    assert TestClient(app).post("/write").status_code == 200
    assert events == ["handler", "commit", "response"]


def test_a_new_account_can_be_used_by_the_very_next_requests(client):
    def register_then_act(n):
        reply = client.post(f"{API}/auth/register", json={"email": f"order-{n}-{id(client)}@order.test", "password": "long-enough-1"})
        headers = {"Authorization": "Bearer " + reply.json()["access_token"]}
        return client.get(f"{API}/courses", headers=headers).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert set(pool.map(register_then_act, range(10))) == {200}
