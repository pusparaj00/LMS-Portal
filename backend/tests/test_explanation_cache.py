"""F-46, TR-L-09, TR-V-11, F-62: the failure-signature cache and instructor review of stored explanations."""
import pytest
from sqlalchemy import text

from app.feedback.signature_cache import normalise_message
from app.llm.adapter import LLMError
from tests.test_feedback_api import (  # noqa: F401  (fixtures)
    WRONG,
    FakeLLM,
    explain,
    failed_submission,
    good_reply,
    llm,
    new_student,
    world,
)

API = "/api/v1"
CLAIM = "Your program prints a fixed word instead of using the number it reads."


def first_explanation(client, make_user, world, owner, llm, code=WRONG):
    """A live, verified explanation, which the cache then stores."""
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers, code=code)
    llm(FakeLLM(good_reply(owner, sid, world)))
    body = explain(client, headers, sid).json()
    assert body["status"] == "verified" and body["cached"] is False
    return sid


def entry(owner, problem_id):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT signature, status, hit_count, explanation_json FROM explanation_cache WHERE problem_id = :p"),
            {"p": problem_id},
        ).one()


def test_the_next_student_with_the_same_failure_gets_the_stored_explanation_without_a_model_call(
    client, make_user, world, owner, llm
):
    first_explanation(client, make_user, world, owner, llm)
    stored = entry(owner, world["p"])
    assert stored.status == "auto_verified" and stored.explanation_json["line_text"] == "print('wrong')"

    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers, code="print('wrong')   \n")  # same mistake, other spacing
    fake = llm(FakeLLM(LLMError("the model must not be called")))
    body = explain(client, headers, sid).json()
    assert body["cached"] is True and body["status"] == "verified" and body["attempts"] == 0
    assert body["explanation"]["claim"] == CLAIM and body["explanation"]["concept"] == "loops"
    assert fake.calls == []
    assert entry(owner, world["p"]).hit_count == 1
    with owner.connect() as conn:
        rows = conn.execute(
            text("SELECT check_name, passed, model, prompt_version, detail FROM explanation_checks WHERE submission_id = :s"),
            {"s": sid},
        ).all()
    assert {(r.model, r.prompt_version) for r in rows} == {("cache", "cache-v1")} and all(r.passed for r in rows)
    assert "failure-signature cache" in rows[-1].detail


def test_the_same_failure_in_different_code_is_not_given_a_line_that_does_not_match(
    client, make_user, world, owner, llm
):
    first_explanation(client, make_user, world, owner, llm)
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers, code="x = 1\nprint('wrong')\n")  # line 1 is now different
    fake = llm(FakeLLM(good_reply(owner, sid, world, line=2)))
    body = explain(client, headers, sid).json()
    assert body["cached"] is False and len(fake.calls) == 1  # the live flow ran


def test_a_rejected_entry_is_never_reused(client, make_user, world, owner, llm):
    first_explanation(client, make_user, world, owner, llm)
    signature = entry(owner, world["p"]).signature
    rejected = client.post(f"{API}/explanations/{signature}/approve", headers=world["instructor"], json={"decision": "reject"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    fake = llm(FakeLLM(good_reply(owner, sid, world)))
    assert explain(client, headers, sid).json()["cached"] is False and len(fake.calls) == 1


def test_the_instructor_sees_the_entries_and_an_edited_claim_is_used_from_then_on(client, make_user, world, owner, llm):
    first_explanation(client, make_user, world, owner, llm)
    listed = client.get(f"{API}/courses/{world['course']}/explanations", headers=world["instructor"])
    assert listed.status_code == 200
    [item] = [e for e in listed.json() if e["problem_id"] == world["p"]]
    assert item["claim"] == CLAIM and item["status"] == "auto_verified" and item["test_category"] in ("basic", "boundary")
    edited = "Your program always prints the same word; it never uses the number it reads."
    approved = client.post(
        f"{API}/explanations/{item['signature']}/approve", headers=world["instructor"],
        json={"decision": "approve", "claim": edited},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "instructor_approved"
    assert approved.json()["claim"] == edited and approved.json()["approved_by"] is not None
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    llm(FakeLLM(LLMError("not called")))
    assert explain(client, headers, sid).json()["explanation"]["claim"] == edited


@pytest.mark.parametrize(
    "claim",
    [
        "Use this: n = int(input())\nprint(n + 1)",  # the reference solution
        "Your code fails for 987654 because it should print 987655.",  # hidden test data
        "x" * 401,
    ],
)
def test_an_edit_that_fails_the_checks_is_refused_and_nothing_changes(client, make_user, world, owner, llm, claim):
    first_explanation(client, make_user, world, owner, llm)
    signature = entry(owner, world["p"]).signature
    response = client.post(
        f"{API}/explanations/{signature}/approve", headers=world["instructor"], json={"decision": "approve", "claim": claim}
    )
    assert response.status_code == 422
    stored = entry(owner, world["p"])
    assert stored.status == "auto_verified" and stored.explanation_json["claim"] == CLAIM


def test_rejecting_with_an_edit_is_refused(client, make_user, world, owner, llm):
    first_explanation(client, make_user, world, owner, llm)
    signature = entry(owner, world["p"]).signature
    response = client.post(
        f"{API}/explanations/{signature}/approve", headers=world["instructor"],
        json={"decision": "reject", "claim": "a different text"},
    )
    assert response.status_code == 422


def test_only_the_courses_instructor_can_review_its_entries(client, make_user, world, owner, llm):
    first_explanation(client, make_user, world, owner, llm)
    signature = entry(owner, world["p"]).signature
    _, other = make_user("instructor")
    _, student = make_user("student")
    url = f"{API}/explanations/{signature}/approve"
    assert client.post(url, headers=other, json={"decision": "reject"}).status_code == 404
    assert client.post(url, headers=student, json={"decision": "reject"}).status_code == 403
    assert client.get(f"{API}/courses/{world['course']}/explanations", headers=other).status_code == 403
    assert client.post(f"{API}/explanations/no-such-signature/approve", headers=world["instructor"],
                       json={"decision": "approve"}).status_code == 404
    assert entry(owner, world["p"]).status == "auto_verified"


def test_a_template_fallback_is_not_stored(client, make_user, world, owner, llm):
    _, headers = new_student(client, make_user, world)
    sid = failed_submission(client, world, headers)
    bad = good_reply(owner, sid, world, line=9999)
    llm(FakeLLM(bad, bad))
    assert explain(client, headers, sid).json()["status"] == "fallback"
    with owner.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM explanation_cache WHERE problem_id = :p"), {"p": world["p"]})
        assert count.scalar_one() == 0


@pytest.mark.parametrize(
    "stderr,expected",
    [
        ('Traceback (most recent call last):\n  File "/work/a1/main.py", line 3, in <module>\nNameError: name \'x\' is not defined\n',
         "NameError: name 'x' is not defined"),
        ("ZeroDivisionError: division by zero\n\n", "ZeroDivisionError: division by zero"),
        ("IndexError: list index out of range at 17\n", "IndexError: list index out of range at #"),
        ("", ""),
    ],
)
def test_the_error_message_is_normalised_so_runs_of_the_same_mistake_match(stderr, expected):
    assert normalise_message(stderr) == expected
