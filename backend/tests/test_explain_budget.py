"""TR-P-03, TR-L-12: a new explanation, both attempts included, ends within its time budget; a slow model gives the
template in time instead of a late answer."""
import time

import pytest

from app.config import get_settings
from app.llm import adapter as llm_adapter
from app.llm.adapter import FallbackChain, LLMConfig, LLMError
from tests.test_feedback_api import (  # noqa: F401  (fixtures)
    check_rows,
    explain,
    failed_submission,
    good_reply,
    llm,
    new_student,
    world,
)

BUDGET = 3.0


class SlowLLM:
    """Answers after `delay` seconds, but like the real adapters it stops waiting at the deadline."""

    def __init__(self, delay, reply="{}"):
        self.delay, self.reply = delay, reply
        self.config = LLMConfig("slow", "slow-model", 30.0, 0, 0.1)
        self.calls = 0

    def complete(self, system, user, json_schema=None):
        self.calls += 1
        timeout = llm_adapter._time_left(self.config.timeout_s)
        if self.delay > timeout:
            time.sleep(timeout)
            raise LLMError("timed out")
        time.sleep(self.delay)
        return self.reply


def test_a_deadline_caps_every_call_inside_it_and_an_inner_one_never_extends_an_outer_one():
    assert llm_adapter._time_left(12) == 12
    with llm_adapter.deadline_within(5):
        assert 4 < llm_adapter._time_left(12) <= 5
        with llm_adapter.deadline_within(30):
            assert llm_adapter._time_left(12) <= 5
        with llm_adapter.deadline_within(0.5), pytest.raises(LLMError, match="budget"):
            llm_adapter._time_left(12)
    assert llm_adapter._time_left(12) == 12


def test_the_fallback_chain_keeps_to_a_deadline_set_by_its_caller():
    chain = FallbackChain([SlowLLM(10)], budget_s=20)
    started = time.monotonic()
    with llm_adapter.deadline_within(2), pytest.raises(LLMError):
        chain.complete("s", "u")
    assert time.monotonic() - started < 2.5


@pytest.fixture
def short_budget(monkeypatch):
    monkeypatch.setattr(get_settings(), "explain_budget_s", BUDGET)


def test_a_model_slower_than_the_budget_gives_the_template_in_time(client, make_user, world, owner, llm, short_budget):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    slow = llm(SlowLLM(10))
    started = time.monotonic()
    body = explain(client, headers, sid).json()
    assert time.monotonic() - started < BUDGET + 1
    assert body["status"] == "fallback" and body["fallback_text"] and body["explanation"] is None
    assert slow.calls == 1  # no second attempt that could not finish
    names = [(r["check_name"], r["passed"]) for r in check_rows(owner, sid)]
    assert ("llm_call", False) in names and ("time_budget", False) in names and names[-1] == ("final", False)


def test_a_model_inside_the_budget_is_still_verified(client, make_user, world, owner, llm, short_budget):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    llm(SlowLLM(0.5, good_reply(owner, sid, world)))
    assert explain(client, headers, sid).json()["status"] == "verified"
