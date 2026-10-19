"""F-62, TR-L-06: a problem's leak policy can only make the guard stricter than the threshold tuned on the bank."""
import pytest

from app.feedback import leak
from tests.test_feedback_api import (  # noqa: F401  (fixtures)
    Q_REFERENCE,
    FakeLLM,
    explain,
    failed_submission,
    good_reply,
    llm,
    new_student,
    world,
)

API = "/api/v1"
# Measured with the guard itself: 0.636 similar to the list-sum solution, so between Strict (0.5) and Standard (0.7).
LOOP = "total = 0\nfor v in values:\n    total = total + v"
# Measured at 0.727: already blocked at the tuned 0.7.
CLOSE = "values = [int(x) for x in input().split()]\nprint(sum(values))"
# Three inline snippets, measured at about 0.53 similar to the add-one solution.
P_CLAIM = ("Read the number, add one, then print it: `n = int(input())`, then `result = n + 1`, "
           "then `print(result)`.")
# The student's own program holds these lines (and prints an extra 0, so it fails): a claim may quote them
P_STUDENT = "n = int(input())\nresult = n + 1\nprint(result)\nprint(0)\n"


def similarity(text, reference):
    lines, snippets = leak.code_like_text(text)
    return leak.containment("\n".join([*lines, *snippets]), reference)


def test_a_stricter_threshold_blocks_what_the_default_lets_through():
    assert 0.5 <= similarity(LOOP, Q_REFERENCE) < 0.7
    assert leak.check(LOOP, Q_REFERENCE).passed
    assert leak.check(LOOP, Q_REFERENCE, 0.7).passed
    assert not leak.check(LOOP, Q_REFERENCE, 0.5).passed
    assert not leak.check(LOOP, Q_REFERENCE, 0.3).passed


def test_the_guard_can_never_be_made_looser_than_the_tuned_default():
    assert 0.7 <= similarity(CLOSE, Q_REFERENCE) < 0.9
    assert not leak.check(CLOSE, Q_REFERENCE).passed
    assert not leak.check(CLOSE, Q_REFERENCE, 0.9).passed  # asking for 0.9 still means 0.7
    assert not leak.check("```\nprint(1)\n```", Q_REFERENCE, 0.7).passed  # the absolute rules stay absolute


def test_the_policy_is_read_and_set_by_the_courses_teacher_only(client, make_user, world):
    path = f"{API}/problems/{world['p']}/policy"
    teacher = world["instructor"]
    assert client.get(path, headers=teacher).json() == {
        "max_hint_level": 3, "leak_threshold": None, "effective_leak_threshold": 0.7}
    strict = client.put(path, headers=teacher, json={"max_hint_level": 2, "leak_threshold": 0.5})
    assert strict.json() == {"max_hint_level": 2, "leak_threshold": 0.5, "effective_leak_threshold": 0.5}
    for bad in (0.8, 0.2):  # looser than the tuned default, or below the strictest level
        assert client.put(path, headers=teacher, json={"max_hint_level": 3, "leak_threshold": bad}).status_code == 422
    _, other = make_user("instructor")
    _, student = new_student(client, make_user, world)
    assert client.put(path, headers=other, json={"max_hint_level": 3}).status_code == 404
    assert client.put(path, headers=student, json={"max_hint_level": 3}).status_code == 403
    reset = client.put(path, headers=teacher, json={"max_hint_level": 3, "leak_threshold": None}).json()
    assert reset["effective_leak_threshold"] == 0.7


@pytest.mark.parametrize(("threshold", "expected"), [(None, "verified"), (0.5, "fallback")])
def test_an_explanation_quoting_part_of_the_solution_obeys_the_problems_policy(
    client, make_user, world, owner, llm, threshold, expected
):
    from tests.test_feedback_api import P_REFERENCE

    assert 0.5 <= similarity(P_CLAIM, P_REFERENCE) < 0.7
    client.put(f"{API}/problems/{world['p']}/policy", headers=world["instructor"],
               json={"max_hint_level": 3, "leak_threshold": threshold})
    try:
        _, headers = new_student(client, make_user, world)
        sid = failed_submission(client, world, headers, code=P_STUDENT)
        reply = good_reply(owner, sid, world, claim=P_CLAIM)
        llm(FakeLLM(reply, reply, reply))
        body = explain(client, headers, sid).json()
        assert body["status"] == expected
    finally:
        client.put(f"{API}/problems/{world['p']}/policy", headers=world["instructor"],
                   json={"max_hint_level": 3, "leak_threshold": None})
