"""TR-L-04, TR-L-06, F-43, F-44: the verifier against scripted replies. No real model is involved."""
import json

import pytest

from app.feedback.verifier import Evidence, FailedTest, all_passed, verify

CODE = "n = int(input())\ntotal = 0\nfor i in range(n):\n    total += i\nprint(total)\n"
REFERENCE = "n = int(input())\ntotal = 0\nfor i in range(1, n + 1):\n    total += i\nprint(total)\n"
LOOPS, STRINGS = 11, 12
EVIDENCE = Evidence(
    code=CODE,
    reference_solution=REFERENCE,
    failed_tests=[
        FailedTest(101, "basic", False, "5\n", "15\n", frozenset({LOOPS})),
        FailedTest(102, "large_input", True, "100000\n", "5000050000\n", frozenset({LOOPS})),
    ],
    error_concept_ids=frozenset(),
    retrieved_chunk_ids=frozenset({7, 8}),
)

GOOD = {
    "failing_test_id": 101,
    "line": 3,
    "concept_id": LOOPS,
    "claim": "The loop on this line stops one value early because range leaves out its upper limit.",
    "source_chunk_ids": [7],
    "hint_level": 2,
}


def reply(**changes) -> str:
    return json.dumps({**GOOD, **changes})


def failed_checks(raw: str) -> set[str]:
    _, checks = verify(raw, EVIDENCE)
    return {c.name for c in checks if not c.passed}


def test_a_correct_reply_is_accepted():
    explanation, checks = verify(reply(), EVIDENCE)
    assert explanation is not None and all_passed(checks)
    assert {c.name for c in checks} >= {
        "json_valid", "test_exists", "line_exists", "concept_matches", "sources_real", "no_code_leak"
    }


def test_a_nonexistent_test_id_is_rejected():
    # the concept is looked up through the cited test, so it cannot match either
    assert failed_checks(reply(failing_test_id=999)) == {"test_exists", "concept_matches"}


def test_a_test_that_passed_is_not_a_failing_test():
    assert "test_exists" in failed_checks(reply(failing_test_id=103))


@pytest.mark.parametrize("line", [0, -1, 6, 400])
def test_a_line_outside_the_code_is_rejected(line):
    assert failed_checks(reply(line=line)) == {"line_exists"}


def test_a_concept_not_linked_to_the_failed_category_is_rejected():
    assert failed_checks(reply(concept_id=STRINGS)) == {"concept_matches"}


def test_a_chunk_that_was_not_retrieved_is_rejected():
    assert failed_checks(reply(source_chunk_ids=[7, 999])) == {"sources_real"}


def test_no_sources_is_fine_when_none_apply():
    assert failed_checks(reply(source_chunk_ids=[])) == set()


def test_a_reply_containing_the_full_solution_is_rejected():
    claim = "Use this instead:\n```python\n" + REFERENCE + "```"
    assert "no_code_leak" in failed_checks(reply(claim=claim))


def test_a_solution_pasted_without_a_fence_is_rejected():
    assert "no_code_leak" in failed_checks(reply(claim="Try this:\n" + REFERENCE))


def test_a_renamed_copy_of_the_solution_is_rejected():
    renamed = "m = int(input())\ns = 0\nfor k in range(1, m + 1):\n    s += k\nprint(s)"
    assert "no_code_leak" in failed_checks(reply(claim=renamed))


@pytest.mark.parametrize("raw", ["not json at all", "[]", "", "{}", '{"failing_test_id": 101}'])
def test_malformed_replies_are_rejected(raw):
    explanation, checks = verify(raw, EVIDENCE)
    assert explanation is None
    assert [c.name for c in checks] == ["json_valid"] and not checks[0].passed


@pytest.mark.parametrize("field,value", [("line", "3"), ("line", True), ("claim", 5), ("source_chunk_ids", "7"),
                                          ("source_chunk_ids", ["7"]), ("hint_level", 1.5)])
def test_wrongly_typed_fields_are_rejected(field, value):
    assert failed_checks(reply(**{field: value})) == {"json_valid"}


def test_hint_level_three_is_never_accepted_from_the_model():
    assert failed_checks(reply(hint_level=3)) == {"hint_level_ok"}


def test_an_empty_or_overlong_claim_is_rejected():
    assert failed_checks(reply(claim="   ")) == {"claim_length"}
    assert failed_checks(reply(claim="The loop is wrong. " * 40)) == {"claim_length"}


def test_a_claim_that_repeats_hidden_test_data_is_rejected():
    assert failed_checks(reply(claim="It fails when the input is 100000 and the answer is 5000050000.")) == {
        "no_hidden_test_leak"
    }


def test_visible_test_data_may_be_mentioned():
    assert failed_checks(reply(claim="For the input 5 you print 10 where 15 is expected.")) == set()


def test_a_claim_that_repeats_a_passed_hidden_input_is_rejected():
    evidence = Evidence(
        code=CODE, reference_solution=REFERENCE, failed_tests=EVIDENCE.failed_tests,
        error_concept_ids=EVIDENCE.error_concept_ids, retrieved_chunk_ids=EVIDENCE.retrieved_chunk_ids,
        hidden_inputs=frozenset({"77777\n"}),
    )
    _, checks = verify(reply(claim="It fails when the input is 77777."), evidence)
    assert "no_hidden_test_leak" in {c.name for c in checks if not c.passed}


def test_a_syntax_error_allows_only_the_syntax_concept():
    evidence = Evidence(
        code=CODE, reference_solution=REFERENCE,
        failed_tests=[FailedTest(101, "basic", False, "5\n", "15\n", frozenset({LOOPS}))],
        error_concept_ids=frozenset({STRINGS}), retrieved_chunk_ids=frozenset(),
        error_type="syntax_error",
    )
    _, checks = verify(reply(concept_id=LOOPS, source_chunk_ids=[]), evidence)
    assert "concept_matches" in {c.name for c in checks if not c.passed}
    _, checks = verify(reply(concept_id=STRINGS, source_chunk_ids=[]), evidence)
    assert all_passed(checks)


def test_the_error_types_concept_is_also_acceptable():
    evidence = Evidence(
        code=CODE, reference_solution=REFERENCE, failed_tests=EVIDENCE.failed_tests,
        error_concept_ids=frozenset({STRINGS}), retrieved_chunk_ids=EVIDENCE.retrieved_chunk_ids,
    )
    _, checks = verify(reply(concept_id=STRINGS), evidence)
    assert all_passed(checks)


def test_every_failed_check_is_reported_not_just_the_first():
    assert failed_checks(reply(failing_test_id=999, line=0, concept_id=STRINGS, source_chunk_ids=[999])) == {
        "test_exists", "line_exists", "concept_matches", "sources_real"
    }


@pytest.mark.parametrize("claim", [
    "The loop `for i in range(n)` stops one value early.",
    "`range` leaves out its upper limit, so `total += i` misses `n`.",
    "Line 2 sets `total` to `0`, and `len()` is not used. A `ValueError` is not raised.",
])
def test_code_the_claim_quotes_may_come_from_the_students_program_or_plain_python(claim):
    assert "quoted_code_is_theirs" not in failed_checks(reply(claim=claim))


@pytest.mark.parametrize("claim", [
    "Use `sorted(values)` here instead of the loop.",
    "The call `total.add(i)` is wrong because totals have no add method.",
])
def test_code_the_claim_quotes_that_is_not_in_the_students_program_is_rejected(claim):
    assert failed_checks(reply(claim=claim)) == {"quoted_code_is_theirs"}


def testable(error_type=None, prediction=True) -> Evidence:
    return Evidence(
        code=CODE, reference_solution=REFERENCE, failed_tests=EVIDENCE.failed_tests, error_concept_ids=frozenset(),
        retrieved_chunk_ids=frozenset({7, 8}), error_type=error_type, require_example=True, require_prediction=prediction,
    )


def test_a_claim_without_an_example_and_a_prediction_is_not_testable_when_they_are_required():
    _, checks = verify(reply(), testable())
    missing = next(c for c in checks if c.name == "claim_testable")
    assert not missing.passed and missing.detail == "missing: example_input, predicted_output"
    _, checks = verify(reply(example_input="5"), testable())
    assert next(c for c in checks if c.name == "claim_testable").detail == "missing: predicted_output"


def test_an_empty_prediction_is_a_prediction_the_program_prints_nothing():
    _, checks = verify(reply(example_input="5", predicted_output=""), testable())
    assert all_passed(checks)


def test_a_cached_claim_needs_an_example_but_no_prediction():
    _, checks = verify(reply(example_input="5"), testable(prediction=False))
    assert all_passed(checks)
    _, checks = verify(reply(), testable(prediction=False))
    assert "claim_testable" in {c.name for c in checks if not c.passed}


def test_a_syntax_error_needs_no_example_because_no_program_runs():
    _, checks = verify(reply(), testable(error_type="syntax_error"))
    assert "claim_testable" not in {c.name for c in checks}


def test_the_check_is_not_added_when_nothing_is_required():
    _, checks = verify(reply(), EVIDENCE)
    assert "claim_testable" not in {c.name for c in checks}


def test_a_prediction_that_is_not_text_is_rejected():
    assert failed_checks(reply(predicted_output=5)) == {"json_valid"}


def test_a_value_the_student_can_already_see_is_not_a_hidden_value_but_a_hidden_input_still_is():
    evidence = Evidence(
        code=CODE, reference_solution=REFERENCE, failed_tests=EVIDENCE.failed_tests, error_concept_ids=frozenset(),
        retrieved_chunk_ids=frozenset({7, 8}), visible_texts=frozenset({"5000050000"}),
    )
    seen = reply(claim="A sum such as 5000050000 needs the loop to reach the last number.")
    assert all_passed(verify(seen, evidence)[1])
    assert not all_passed(verify(seen, EVIDENCE)[1])  # without the visible texts the same claim is held back
    _, checks = verify(reply(claim="It breaks for the input 100000."), evidence)
    assert "no_hidden_test_leak" in {c.name for c in checks if not c.passed}
