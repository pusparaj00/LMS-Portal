"""A crowd asking the assistant at once must not use every worker thread and database connection.

Found by the agent simulation (docs/results/step-60-simulation.md): 48 concurrent model-backed chats exhausted the
default pool of 15 connections, so cheap requests waited 30 s and then got a 500."""
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.auth import get_conn
from app.config import get_settings
from app.db import get_chat_engine, get_engine
from app.llm import adapter as llm
from app.llm.adapter import FallbackChain, LLMConfig, LLMError
from app.main import app


class Slow:
    config = LLMConfig("slow", "slow-model", 1.0, 0, 0.1)

    def __init__(self, seconds):
        self.seconds = seconds

    def complete(self, system, user, json_schema=None):
        time.sleep(self.seconds)
        return "ok"


@pytest.fixture(autouse=True)
def fresh_slots():
    llm._slots = None
    yield
    llm._slots = None


def test_model_calls_beyond_the_cap_fail_fast_instead_of_queueing():
    chain = FallbackChain([Slow(1.0)], budget_s=5, max_concurrent=2, queue_wait_s=0.1)
    answers = []
    running = [threading.Thread(target=lambda: answers.append(chain.complete("s", "u"))) for _ in range(2)]
    [t.start() for t in running]
    time.sleep(0.2)
    started = time.monotonic()
    with pytest.raises(LLMError, match="waiting"):
        chain.complete("s", "u")
    assert time.monotonic() - started < 0.6
    [t.join() for t in running]
    assert answers == ["ok", "ok"]


def test_a_slot_is_free_again_once_a_call_ends():
    chain = FallbackChain([Slow(0.05)], budget_s=5, max_concurrent=1, queue_wait_s=0.1)
    assert [chain.complete("s", "u") for _ in range(3)] == ["ok"] * 3


def test_an_exhausted_connection_pool_answers_503_with_retry_after(make_user):
    _, headers = make_user("student")

    def exhausted():
        raise PoolTimeout("QueuePool limit reached", None, None)
        yield

    app.dependency_overrides[get_conn] = exhausted
    try:
        response = TestClient(app).get("/api/v1/me", headers=headers)
    finally:
        app.dependency_overrides.pop(get_conn, None)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"
    assert response.json()["error"]["code"] == "busy"


def test_the_pool_covers_the_servers_worker_threads_and_fails_fast():
    settings = get_settings()
    pool = get_engine().pool
    assert pool.size() + pool._max_overflow >= 40
    assert pool.timeout() == settings.db_pool_timeout_s <= 10
    chat_pool = get_chat_engine().pool
    assert chat_pool.size() + chat_pool._max_overflow >= 40  # a chat request holds a connection from each pool
