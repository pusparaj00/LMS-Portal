"""TR-L-05: a claim that names an input is tried on that input in the sandbox before a student sees it."""
import pytest
from sqlalchemy import text

from app.feedback import claim_check, signature_cache
from app.feedback.context import load_context
from app.sandbox import SandboxUnavailable
from tests.test_feedback_api import (  # noqa: F401  (fixtures)
    WRONG,
    FakeLLM,
    check_rows,
    explain,
    failed_submission,
    good_reply,
    llm,
    new_student,
    world,
)

API = "/api/v1"
PRINTS_TWO = "print(2)\n"  # right for input 1 (the visible test), wrong for the hidden one


@pytest.fixture
def sandbox_calls(monkeypatch):
    """Count the runs the claim check asks the sandbox for, while still using the real sandbox."""
    calls = []
    real = claim_check.run_batch

    def counting(code, stdins):
        calls.append(stdins)
        return real(code, stdins)

    monkeypatch.setattr(claim_check, "run_batch", counting)
    return calls


def failures(owner, sid, attempt=1):
    return {r["check_name"]: r["detail"] for r in check_rows(owner, sid) if r["attempt"] == attempt and not r["passed"]}


def test_an_input_on_which_the_program_really_differs_is_verified_and_shown_with_the_students_own_output(
    client, make_user, world, owner, llm, sandbox_calls  # noqa: F811
):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)  # prints 'wrong'
    llm(FakeLLM(good_reply(owner, sid, world, example_input="5")))
    response = explain(client, headers, sid)
    body = response.json()["explanation"]
    assert response.json()["status"] == "verified" and body["example_input"] == "5"
    assert body["example_output"] == "wrong"  # what THEIR program prints; the correct output (6) is not revealed
    assert len(sandbox_calls) == 2  # the student's program and the reference, each once
    rows = check_rows(owner, sid)
    assert any(r["check_name"] == "claimed_input" and r["passed"] for r in rows)
    assert {r["prompt_version"] for r in rows} == {"explain-v4"}


def test_an_input_on_which_the_program_already_gives_the_right_answer_is_rejected_then_retried(
    client, make_user, world, owner, llm  # noqa: F811
):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers, code=PRINTS_TWO)
    fake = llm(FakeLLM(good_reply(owner, sid, world, example_input="1", predicted_output="2"),
                       good_reply(owner, sid, world, example_input="5", predicted_output="2")))
    body = explain(client, headers, sid).json()
    assert body["status"] == "verified" and body["attempts"] == 2 and body["explanation"]["example_input"] == "5"
    assert "same output as the correct program" in failures(owner, sid)["claimed_input"]
    assert "claimed_input" in fake.calls[1][1]  # the retry is told why the first reply was rejected


def test_an_example_that_is_a_hidden_test_input_is_never_shown(client, make_user, world, owner, llm):  # noqa: F811
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    bad = good_reply(owner, sid, world, example_input="987654", claim="SECRET-HIDDEN-EXAMPLE")
    llm(FakeLLM(bad, bad))
    response = explain(client, headers, sid)
    assert response.json()["status"] == "fallback" and "987654" not in response.text
    assert "SECRET-HIDDEN-EXAMPLE" not in response.text
    assert "hidden test data" in failures(owner, sid)["no_hidden_test_leak"]


def test_a_program_that_crashes_on_the_example_counts_and_says_so(client, make_user, world, owner, llm):  # noqa: F811
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers, code="n = int(input())\nprint(missing_name)\n")
    llm(FakeLLM(good_reply(owner, sid, world, example_input="5", predicted_output="")))
    body = explain(client, headers, sid).json()
    assert body["status"] == "verified"
    assert body["explanation"]["example_output"].startswith("(no output: the program stopped with a ")


def test_an_input_the_correct_program_cannot_read_is_rejected(client, make_user, world, owner, llm):  # noqa: F811
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    bad = good_reply(owner, sid, world, example_input="not a number")
    llm(FakeLLM(bad, bad))
    assert explain(client, headers, sid).json()["status"] == "fallback"
    assert "does not run on the example input" in failures(owner, sid)["claimed_input"]


def test_a_reply_without_an_example_is_not_shown_and_nothing_is_run(
    client, make_user, world, owner, llm, sandbox_calls  # noqa: F811
):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    bad = good_reply(owner, sid, world, example_input="", predicted_output=None)
    fake = llm(FakeLLM(bad, bad))
    body = explain(client, headers, sid).json()
    assert body["status"] == "fallback" and body["explanation"] is None and sandbox_calls == []
    assert failures(owner, sid)["claim_testable"] == "missing: example_input, predicted_output"
    assert "claim_testable" in fake.calls[1][1]  # the retry says what to add


def test_a_wrong_prediction_of_the_output_is_rejected_and_the_retry_is_told_what_the_program_prints(
    client, make_user, world, owner, llm  # noqa: F811
):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)  # prints 'wrong'
    fake = llm(FakeLLM(good_reply(owner, sid, world, predicted_output="5"), good_reply(owner, sid, world)))
    body = explain(client, headers, sid).json()
    assert body["status"] == "verified" and body["attempts"] == 2
    assert "really prints 'wrong'" in failures(owner, sid)["predicted_output"]
    assert "predicted_output" in fake.calls[1][1] and "really prints 'wrong'" in fake.calls[1][1]


@pytest.mark.parametrize(
    "example,check,message",
    [
        (5, "json_valid", "must be text"),
        ("9" * 301, "example_input_ok", "longer than 300"),
    ],
)
def test_a_malformed_or_oversized_example_is_rejected_before_anything_is_run(
    client, make_user, world, owner, llm, sandbox_calls, example, check, message  # noqa: F811
):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    bad = good_reply(owner, sid, world, example_input=example)
    llm(FakeLLM(bad, bad))
    assert explain(client, headers, sid).json()["status"] == "fallback"
    assert message in failures(owner, sid)[check] and sandbox_calls == []


def test_a_claim_that_cannot_be_tried_is_not_shown(client, make_user, world, owner, llm, monkeypatch):  # noqa: F811
    def down(code, stdins):
        raise SandboxUnavailable("down")

    monkeypatch.setattr(claim_check, "run_batch", down)
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    reply = good_reply(owner, sid, world, example_input="5", claim="UNVERIFIED-CLAIM")
    llm(FakeLLM(reply, reply))
    response = explain(client, headers, sid)
    assert response.json()["status"] == "fallback" and "UNVERIFIED-CLAIM" not in response.text
    assert "could not try the example input" in failures(owner, sid)["claimed_input"]


def test_a_stored_explanation_with_an_example_is_served_to_the_next_student_with_their_own_output(
    client, make_user, world, owner, llm, sandbox_calls  # noqa: F811
):
    _, first = new_student(client, make_user, world)
    sid = failed_submission(client, world, first)
    llm(FakeLLM(good_reply(owner, sid, world, example_input="5")))
    assert explain(client, first, sid).json()["status"] == "verified"
    sandbox_calls.clear()

    _, second = new_student(client, make_user, world)
    sid2 = failed_submission(client, world, second)
    fake = llm(FakeLLM("the model must not be called"))
    body = explain(client, second, sid2).json()
    assert body["cached"] is True and fake.calls == []
    assert body["explanation"]["example_input"] == "5" and body["explanation"]["example_output"] == "wrong"
    assert len(sandbox_calls) == 2  # tried again on this student's code, not trusted from the first student


def test_a_stored_example_is_dropped_for_a_student_whose_program_already_handles_it(
    client, make_user, world, owner  # noqa: F811
):
    """The cached claim says 'wrong on input 1'; this student's program prints the right answer for 1."""
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers, code=PRINTS_TWO)
    payload = {
        "claim": "Your program prints a fixed number instead of using the input.", "line": 1, "line_text": "print(2)",
        "concept_id": world["loops"], "hint_level": 2, "test_category": "boundary", "chunk_ids": [],
        "example_input": "1",
    }
    with owner.connect() as conn:
        ctx = load_context(conn, sid, conn.execute(text("SELECT user_id FROM submissions WHERE id = :s"), {"s": sid}).scalar_one())
        explanation, checks, _, example = signature_cache.check_against(conn, ctx, payload)
    assert example is None and not all(c.passed for c in checks)
    assert any(c.name == "claimed_input" and not c.passed for c in checks)
    assert explanation is not None  # it parsed; only the claim check refused it


def test_an_instructor_approving_a_stored_explanation_with_an_example_re_runs_the_check(
    client, make_user, world, owner, llm, sandbox_calls  # noqa: F811
):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    llm(FakeLLM(good_reply(owner, sid, world, example_input="5")))
    explain(client, headers, sid)
    with owner.connect() as conn:
        signature = conn.execute(
            text("SELECT signature FROM explanation_cache WHERE problem_id = :p"), {"p": world["p"]}
        ).scalar_one()
    sandbox_calls.clear()
    approved = client.post(
        f"{API}/explanations/{signature}/approve", headers=world["instructor"], json={"decision": "approve"}
    )
    assert approved.status_code == 200 and approved.json()["status"] == "instructor_approved"
    assert len(sandbox_calls) == 2


def test_the_example_is_part_of_the_reply_format_the_model_is_asked_for():
    from app.feedback.prompt import SYSTEM
    from app.feedback.verifier import JSON_SCHEMA

    for field in ("example_input", "predicted_output"):
        assert field in JSON_SCHEMA["properties"] and field not in JSON_SCHEMA["required"]  # a syntax error needs neither
        assert field in SYSTEM
    assert "hidden test" in SYSTEM


def test_the_prompt_tells_the_model_what_the_students_program_really_printed(
    client, make_user, world, owner, llm  # noqa: F811
):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)  # prints 'wrong'
    fake = llm(FakeLLM(good_reply(owner, sid, world)))
    explain(client, headers, sid)
    assert "the student's program printed 'wrong'" in fake.calls[0][1]
