"""TR-D-03, TR-D-04, TR-V-02: the bank validates and bad problems are rejected."""
from pathlib import Path

import pytest
from sqlalchemy import text

from app.bank_import import import_bank, load_bank, validate_bank
from app.db import get_engine
from app.services.validation import validate_code_problem, validate_mcq_item

ROOT = Path(__file__).resolve().parents[1]
BANK = next(p for p in (ROOT / "data" / "bank", ROOT.parent / "data" / "bank") if p.exists())
CONCEPTS = {"loops"}
GOOD_TESTS = [{"input": "2\n", "expected": "3\n", "hidden": False, "category": "basic"}]


@pytest.fixture(scope="module")
def bank():
    return load_bank(BANK)


@pytest.fixture(scope="module")
def verdicts(bank):
    return validate_bank(bank)


def test_whole_bank_validates(verdicts):
    rejected = [(v.title, v.errors) for v in verdicts if v.errors]
    assert rejected == []
    assert sum(v.kind == "code" for v in verdicts) >= 30
    assert sum(v.kind == "mcq" for v in verdicts) >= 10


def test_every_problem_has_concepts_categories_and_a_prior_flag(bank):
    for p in bank.problems:
        assert p["concepts"] and all(t["category"] for t in p["tests"]), p["title"]
        assert any(not t["hidden"] for t in p["tests"]), p["title"]
        assert any(t["hidden"] for t in p["tests"]), p["title"]
    names = [p["title"] for p in bank.problems + bank.items]
    assert len(names) == len(set(names))


def test_every_wrong_option_names_a_known_misconception(bank):
    known = {m["name"] for m in bank.misconceptions}
    for item in bank.items:
        wrong = [o for o in item["options"] if not o["correct"]]
        assert wrong and all(o["misconception"] in known for o in wrong), item["title"]


def test_rejects_wrong_reference_solution():
    errors = validate_code_problem(
        concept_names=["loops"], known_concepts=CONCEPTS,
        reference_solution="print(int(input()))\n", tests=GOOD_TESTS,
    )
    assert len(errors) == 1 and errors[0].startswith("reference solution fails test 1 (basic): it printed ")
    assert "but the test expects" in errors[0]


def test_rejects_missing_concept_category_tests_and_reference():
    base = dict(known_concepts=CONCEPTS, reference_solution="print(3)\n", tests=GOOD_TESTS)
    assert validate_code_problem(concept_names=[], **base) == ["has no concept"]
    assert "unknown concept 'zzz'" in validate_code_problem(concept_names=["zzz"], **base)
    no_category = [{**GOOD_TESTS[0], "category": ""}]
    assert "test 0 has no category" in validate_code_problem(
        concept_names=["loops"], **{**base, "tests": no_category}
    )
    assert "has no tests" in validate_code_problem(
        concept_names=["loops"], **{**base, "tests": []}
    )
    assert validate_code_problem(
        concept_names=["loops"], **{**base, "reference_solution": " "}
    ) == ["has no reference solution"]


def test_rejects_reference_solution_that_crashes_or_hangs():
    for code in ("raise SystemExit(1)\n", "while True:\n    pass\n"):
        errors = validate_code_problem(
            concept_names=["loops"], known_concepts=CONCEPTS, reference_solution=code,
            tests=GOOD_TESTS,
        )
        assert errors and "fails test 1" in errors[0] and "did not finish normally" in errors[0]


def test_rejects_bad_mcq_items():
    base = dict(concept_names=["loops"], known_concepts=CONCEPTS, known_misconceptions={"m"},
                code="print(3)\n")
    good = [
        {"text": "3", "correct": True},
        {"text": "4", "correct": False, "misconception": "m"},
        {"text": "5", "correct": False, "misconception": "m"},
    ]
    assert validate_mcq_item(options=good, **base) == []
    untagged = [good[0], {"text": "4", "correct": False}, good[2]]
    assert any("no misconception" in e for e in validate_mcq_item(options=untagged, **base))
    wrong_key = [{**good[0], "text": "9"}, *good[1:]]
    assert validate_mcq_item(options=wrong_key, **base) == [
        "the correct option is not what the code prints"
    ]


def test_import_loads_everything_flagged_for_review(bank, verdicts, make_user, owner):
    instructor_id, _ = make_user("instructor")
    with owner.connect() as conn:
        email = conn.execute(
            text("SELECT email FROM users WHERE id = :i"), {"i": instructor_id}
        ).scalar_one()
    titles = {v.title for v in verdicts if not v.errors}
    with get_engine().connect() as conn:
        transaction = conn.begin()
        try:
            summary = import_bank(conn, bank, titles, email)
            assert (summary["created"], summary["updated"], summary["unchanged"]) == (75, 0, 0)
            rows = conn.execute(
                text(
                    "SELECT kind, review_status, param_source, count(*) FROM problems"
                    " WHERE course_id = :c GROUP BY 1, 2, 3 ORDER BY 1"
                ),
                {"c": summary["course_id"]},
            ).all()
            assert [tuple(r) for r in rows] == [
                ("code", "needs human review", "prior", 35),
                ("mcq", "needs human review", "prior", 40),
            ]
            untagged = conn.execute(
                text(
                    "SELECT count(*) FROM item_options o JOIN problems p ON p.id = o.problem_id"
                    " WHERE p.course_id = :c AND NOT o.is_correct AND o.misconception_id IS NULL"
                ),
                {"c": summary["course_id"]},
            ).scalar_one()
            assert untagged == 0
            ids = lambda: conn.execute(  # noqa: E731
                text(
                    "SELECT array_agg(t.id ORDER BY t.id) FROM test_cases t JOIN problems p ON p.id = t.problem_id"
                    " WHERE p.course_id = :c"
                ),
                {"c": summary["course_id"]},
            ).scalar_one()
            before = ids()
            conn.execute(
                text("UPDATE problems SET review_status = 'reviewed' WHERE course_id = :c"), {"c": summary["course_id"]}
            )
            again = import_bank(conn, bank, titles, email)
            assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 75)
            assert ids() == before  # nothing was deleted and re-inserted
            reviewed = conn.execute(
                text("SELECT count(*) FROM problems WHERE course_id = :c AND review_status = 'reviewed'"),
                {"c": summary["course_id"]},
            ).scalar_one()
            assert reviewed == 75  # a human review survives running the seed again
        finally:
            transaction.rollback()


def test_a_problem_with_too_many_tests_is_rejected_with_a_clear_message():
    many = [{"input": f"{n}\n", "expected": f"{n + 1}\n", "hidden": True, "category": "basic"} for n in range(51)]
    errors = validate_code_problem(
        concept_names=["loops"], known_concepts=CONCEPTS, reference_solution="print(int(input()) + 1)\n", tests=many
    )
    assert errors == ["has 51 tests; at most 50 are allowed"]


def test_importing_the_bank_into_a_second_course_leaves_the_first_course_its_misconceptions(bank, verdicts, make_user, owner):
    titles = {v.title for v in verdicts if not v.errors}
    emails = []
    for _ in range(2):
        instructor_id, _ = make_user("instructor")
        with owner.connect() as conn:
            emails.append(conn.execute(text("SELECT email FROM users WHERE id = :i"), {"i": instructor_id}).scalar_one())
    count = text(
        "SELECT count(*) FROM misconceptions m JOIN concepts c ON c.id = m.concept_id WHERE c.course_id = :c"
    )
    foreign_links = text(
        "SELECT count(*) FROM item_options o JOIN problems p ON p.id = o.problem_id"
        " JOIN misconceptions m ON m.id = o.misconception_id JOIN concepts c ON c.id = m.concept_id"
        " WHERE p.course_id = :c AND c.course_id <> :c"
    )
    with get_engine().connect() as conn:
        transaction = conn.begin()
        try:
            first = import_bank(conn, bank, titles, emails[0])["course_id"]
            before = conn.execute(count, {"c": first}).scalar_one()
            second = import_bank(conn, bank, titles, emails[1])["course_id"]
            assert before == len(bank.misconceptions) > 0
            assert conn.execute(count, {"c": first}).scalar_one() == before
            assert conn.execute(count, {"c": second}).scalar_one() == before
            assert conn.execute(foreign_links, {"c": first}).scalar_one() == 0
            assert conn.execute(foreign_links, {"c": second}).scalar_one() == 0
        finally:
            transaction.rollback()


def test_every_concept_has_tracing_questions_in_all_three_bands(bank):
    covered = {c["name"] for i in bank.items for c in i["concepts"]}
    assert covered == {c["name"] for c in bank.concepts}  # classes and comprehensions included
    bands = [("easy" if i["difficulty_b"] < -0.5 else "hard" if i["difficulty_b"] > 0.5 else "medium") for i in bank.items]
    assert bands.count("easy") >= 8 and bands.count("medium") >= 8 and bands.count("hard") >= 3
