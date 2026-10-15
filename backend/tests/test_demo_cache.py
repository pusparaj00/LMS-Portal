"""TR-P-07, TR-L-12: cached demo explanations work with the model off, are labelled cached, and are re-verified."""
import json

import pytest
from sqlalchemy import text

from app.feedback import demo_cache
from app.llm.adapter import LLMError
from tests.test_feedback_api import (  # noqa: F401  (fixtures)
    WRONG,
    FakeLLM,
    explain,
    failed_submission,
    llm,
    new_student,
    world,
)

API = "/api/v1"


@pytest.fixture
def cache(tmp_path, monkeypatch):
    def install(*entries):
        (tmp_path / "explanations.json").write_text(json.dumps({"entries": list(entries)}), encoding="utf-8")
        monkeypatch.setenv("DEMO_CACHE_DIR", str(tmp_path))
        demo_cache._entries.cache_clear()

    yield install
    demo_cache._entries.cache_clear()


def entry(**changes):
    base = {
        "problem": "Add one", "code": WRONG, "concept": "loops", "line": 1,
        "claim": "Your program prints a fixed word instead of using the number it reads.", "sources": [],
    }
    return {**base, **changes}


def check_rows(owner, sid):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT check_name, passed, model, prompt_version, detail FROM explanation_checks"
                 " WHERE submission_id = :s ORDER BY id"),
            {"s": sid},
        ).mappings().all()


def test_a_cached_demo_explanation_is_served_without_any_model_call_and_is_labelled(
    client, make_user, world, owner, llm, cache
):
    cache(entry())
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    fake = llm(FakeLLM(LLMError("the model is switched off")))
    body = explain(client, headers, sid).json()
    assert body["cached"] is True and body["status"] == "verified" and body["attempts"] == 0
    assert body["explanation"]["claim"].startswith("Your program prints") and body["explanation"]["concept"] == "loops"
    assert fake.calls == []  # nothing was sent to a model
    rows = check_rows(owner, sid)
    assert {r["model"] for r in rows} == {"cached-demo"} and {r["prompt_version"] for r in rows} == {"demo-v1"}
    assert all(r["passed"] for r in rows)
    assert rows[-1]["check_name"] == "final" and "cached demo explanation" in rows[-1]["detail"]
    assert body["probe"] is not None  # the probe still comes from the bank


def test_whitespace_differences_in_the_code_still_match(client, make_user, world, llm, cache):
    cache(entry(code="print('wrong')   \n\n\n"))
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    llm(FakeLLM(LLMError("off")))
    assert explain(client, headers, sid).json()["cached"] is True


def test_different_code_gets_the_live_flow_not_the_cache(client, make_user, world, owner, llm, cache):
    from tests.test_feedback_api import good_reply

    cache(entry())
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers, code="print('something else')\n")
    fake = llm(FakeLLM(good_reply(owner, sid, world)))
    body = explain(client, headers, sid).json()
    assert body["cached"] is False and len(fake.calls) == 1


@pytest.mark.parametrize("changes", [{"line": 99}, {"concept": "strings"}, {"claim": "Use this: n = int(input()) print(n + 1)"}])
def test_a_cached_explanation_that_does_not_verify_is_not_shown(client, make_user, world, owner, llm, cache, changes):
    from tests.test_feedback_api import good_reply

    cache(entry(**changes))
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    fake = llm(FakeLLM(good_reply(owner, sid, world)))
    body = explain(client, headers, sid).json()
    assert body["cached"] is False and len(fake.calls) == 1  # fell back to the normal verified flow


def test_the_cache_is_off_when_there_is_no_file(client, make_user, world, owner, llm, tmp_path, monkeypatch):
    from tests.test_feedback_api import good_reply

    monkeypatch.setenv("DEMO_CACHE_DIR", str(tmp_path))
    demo_cache._entries.cache_clear()
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    llm(FakeLLM(good_reply(owner, sid, world)))
    assert explain(client, headers, sid).json()["cached"] is False
    demo_cache._entries.cache_clear()


def test_the_committed_demo_file_is_well_formed_and_claims_carry_no_database_ids():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = next(p for p in (root / "data" / "demo", root.parent / "data" / "demo") if p.exists()) / "explanations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["model"] and data["generated"] and len(data["entries"]) >= 3
    for e in data["entries"]:
        assert {"problem", "code", "claim", "line", "concept", "sources"} <= e.keys()
        assert not re.search(r"\btests? \d+", e["claim"]), e["problem"]
