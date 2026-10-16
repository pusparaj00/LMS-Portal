"""TR-A-08: one request ID from the caller, through the API, into the sandbox job; client text is never stored as one."""
import json
import re
import threading
import time

import pytest

from app import sandbox
from app.logging import request_id_var

HEALTH = "/api/v1/health"


def test_a_plain_request_id_is_kept_and_anything_else_is_replaced(client):
    assert client.get(HEALTH, headers={"X-Request-ID": "demo-run_7.2"}).headers["X-Request-ID"] == "demo-run_7.2"
    for offered in ("A" * 65, "two words", "line\nbreak", ""):
        kept = client.get(HEALTH, headers={"X-Request-ID": offered}).headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{32}", kept), offered


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    for name in ("in", "out"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("JOBS_DIR", str(tmp_path))
    return tmp_path


def test_the_sandbox_job_carries_the_request_id(jobs):
    seen = {}

    def runner():
        for _ in range(200):
            found = list((jobs / "in").glob("*.json"))
            if found:
                job = json.loads(found[0].read_text())
                seen.update(job)
                result = {"runs": [{"status": "ok", "stdout": "", "stderr": "", "runtime_ms": 1}]}
                (jobs / "out" / found[0].name).write_text(json.dumps(result))
                return
            time.sleep(0.01)

    thread = threading.Thread(target=runner)
    thread.start()
    token = request_id_var.set("trace-check-1")
    try:
        assert sandbox.run_batch("print(1)", [""])[0].status == "ok"
    finally:
        request_id_var.reset(token)
        thread.join()
    assert seen["request_id"] == "trace-check-1"
