"""G-1: a rejected attempt is retried with an instruction for each failed check, and no hidden data."""
import httpx
import pytest

from app.feedback.prompt import FIXES
from app.llm.adapter import _why
from tests.test_feedback_api import (  # noqa: F401
    FakeLLM,
    explain,
    failed_submission,
    good_reply,
    llm,
    new_student,
    world,
)

HIDDEN_VALUE = "987654"  # a hidden test input of the `world` fixture


def retry_prompt(client, make_user, world, owner, llm, **changes):  # noqa: F811
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    fake = llm(FakeLLM(good_reply(owner, sid, world, **changes), good_reply(owner, sid, world)))
    assert explain(client, headers, sid).json()["status"] == "verified"
    assert len(fake.calls) == 2
    return fake.calls[1][1]


def test_a_reply_that_repeats_hidden_data_is_told_to_describe_the_case_in_words(client, make_user, world, owner, llm):  # noqa: F811
    prompt = retry_prompt(client, make_user, world, owner, llm, claim=f"It fails when the input is {HIDDEN_VALUE}.")
    assert "no_hidden_test_leak" in prompt and FIXES["no_hidden_test_leak"] in prompt
    assert HIDDEN_VALUE not in prompt  # the model is never told which value was hidden


def test_a_reply_that_quotes_invented_code_is_told_to_quote_only_the_students_code(client, make_user, world, owner, llm):  # noqa: F811
    prompt = retry_prompt(client, make_user, world, owner, llm, claim="Try `sorted(set(values))` instead.")
    assert "quoted_code_is_theirs" in prompt and FIXES["quoted_code_is_theirs"] in prompt


def test_every_check_a_reply_can_fail_has_an_instruction():
    names = {"json_valid", "test_exists", "line_exists", "concept_matches", "sources_real", "hint_level_ok",
             "claim_length", "quoted_code_is_theirs", "no_code_leak", "no_hidden_test_leak", "example_input_ok",
             "claimed_input"}
    assert names <= set(FIXES)
    assert all(FIXES[n].strip() for n in names)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (400, {"error": {"message": "Failed to generate JSON", "code": "json_validate_failed"}}, ": Failed to generate JSON"),
        (404, {"error": {"message": "No endpoints found for the model"}}, ": No endpoints found for the model"),
        (400, {"error": "bad request"}, ": bad request"),
        (401, {"error": {"message": "Incorrect API key provided: sk-abcd1234"}}, ""),
        (429, {"error": {"message": "rate limited"}}, ""),
        (400, "not json", ""),
    ],
)
def test_a_provider_reason_is_shown_for_a_bad_request_but_never_for_a_rejected_key(status, body, expected):
    response = httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body)
    assert _why(response) == expected
