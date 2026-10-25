"""TR-L-10: a model drafts a practice problem for one concept; it is offered to the instructor only after its reference
solution passes every one of its tests and a deliberately wrong solution fails in the category the draft names.

Nothing is saved here. The instructor reviews the draft in the problem form and saves it through the ordinary create
path, which checks the reference solution again (TR-D-04). No student data is sent: only the concept's name and the
titles of the course's existing problems, so the draft does not repeat one.
"""
import json
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import Connection, text

from app.grading import TestSpec, grade
from app.llm.adapter import LLMAdapter
from app.schemas import TestCaseIn
from app.services.validation import validate_code_problem

ATTEMPTS = 2  # one retry with the reasons, as for explanations (TR-P-08)
MIN_TESTS, MAX_DRAFT_TESTS = 4, 8

LANGUAGE_NAMES = {"python": "Python", "java": "Java", "c": "C"}
IO_RULES = {
    "python": "The program reads standard input with input() and prints the answer. No prompts in input(), no files, "
              "no imports beyond the standard library.",
    "java": "The program is one file with `public class Main` and a main method, reads standard input with Scanner or "
            "BufferedReader and prints the answer. No prompts, no files, standard library only.",
    "c": "The program is one file with a main function, reads standard input with scanf or fgets and prints the "
         "answer. No prompts, no files, the C standard library only.",
}
SYSTEM_TEMPLATE = """You write one short {language} practice problem for a beginners' course, on the concept named in <concept>.

Rules:
1. {io_rule}
2. Give 4 to 8 tests. Each test has input, the exact expected output, hidden (true or false) and a short snake_case
   category such as basic, empty_input, boundary, negative_numbers, duplicates. At least two tests are hidden, and at
   least one test is in a category other than basic.
3. reference_solution must pass every test exactly. Keep it under 20 lines.
4. wrong_solution is the same program with ONE realistic beginner mistake. It must fail the tests in wrong_category
   and should pass the basic ones.
5. The title must not be one of the titles in <existing_titles>.
6. Reply with JSON only."""


def system_for(language: str) -> str:
    return SYSTEM_TEMPLATE.format(language=LANGUAGE_NAMES[language], io_rule=IO_RULES[language])

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "statement": {"type": "string"},
        "reference_solution": {"type": "string"},
        "wrong_solution": {"type": "string"},
        "wrong_category": {"type": "string"},
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                    "expected": {"type": "string"},
                    "hidden": {"type": "boolean"},
                    "category": {"type": "string"},
                },
                "required": ["input", "expected", "hidden", "category"],
            },
        },
    },
    "required": ["title", "statement", "reference_solution", "wrong_solution", "wrong_category", "tests"],
}


class DraftRejected(Exception):
    """Every attempt failed a check; the reasons say which."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass
class Draft:
    title: str
    statement: str
    reference_solution: str
    tests: list[TestCaseIn]
    wrong_category: str
    checks: list[str]
    attempts: int


def _parse(raw: str) -> dict:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in SCHEMA["required"][:5]):
            raise ValueError("a field is missing or is not text")
        data["tests"] = [TestCaseIn.model_validate(t) for t in data.get("tests") or []]
        return data
    except (ValueError, ValidationError) as exc:
        raise DraftRejected([f"the reply could not be read ({str(exc).splitlines()[0]})"]) from None


def check(data: dict, concept: str, titles: set[str], language: str = "python") -> list[str]:
    """Every reason the draft cannot be offered; empty when it passes. Both programs run only in the sandbox."""
    tests = [t.model_dump() for t in data["tests"]]
    reasons = []
    if not data["title"].strip() or data["title"].strip().lower() in titles:
        reasons.append("the title is empty or already used in this course")
    if not MIN_TESTS <= len(tests) <= MAX_DRAFT_TESTS:
        reasons.append(f"it has {len(tests)} tests; {MIN_TESTS} to {MAX_DRAFT_TESTS} are needed")
    if sum(t["hidden"] for t in tests) < 2:
        reasons.append("fewer than two tests are hidden")
    if data["wrong_category"] not in {t["category"] for t in tests}:
        reasons.append(f"no test is in the category '{data['wrong_category']}' that the wrong solution should fail")
    if reasons:
        return reasons
    reasons += validate_code_problem(
        concept_names=[concept], known_concepts={concept}, reference_solution=data["reference_solution"], tests=tests,
        language=language,
    )
    wrong = grade(
        data["wrong_solution"], [TestSpec(None, t["input"], t["expected"], t["hidden"], t["category"]) for t in tests],
        language,
    )
    if wrong.status == "passed":
        reasons.append("the wrong solution passes every test, so the tests would not catch that mistake")
    elif data["wrong_category"] not in wrong.failed_categories:
        reasons.append(
            f"the wrong solution fails in {', '.join(wrong.failed_categories) or 'no category'}, "
            f"not in '{data['wrong_category']}'"
        )
    return reasons


def draft(conn: Connection, adapter: LLMAdapter, course_id: int, concept: str) -> Draft:
    language = conn.execute(text("SELECT language FROM courses WHERE id = :c"), {"c": course_id}).scalar_one()
    system = system_for(language)
    titles = {
        t.lower()
        for t in conn.execute(text("SELECT title FROM problems WHERE course_id = :c"), {"c": course_id}).scalars()
    }
    user = (
        f"<concept>{concept.replace('_', ' ')}</concept>\n"
        f"<existing_titles>{json.dumps(sorted(titles))}</existing_titles>"
    )
    reasons: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        if reasons:
            user += "\n<previous_attempt_rejected>" + json.dumps(reasons) + "</previous_attempt_rejected>"
        try:
            data = _parse(adapter.complete(system, user, SCHEMA))
            reasons = check(data, concept, titles, language)
        except DraftRejected as exc:
            reasons = exc.reasons
        if not reasons:
            total = len(data["tests"])
            return Draft(
                title=data["title"].strip(), statement=data["statement"].strip(),
                reference_solution=data["reference_solution"], tests=data["tests"],
                wrong_category=data["wrong_category"], attempts=attempt,
                checks=[
                    f"The reference solution passes {total} of {total} tests in the sandbox.",
                    f"A solution with a typical mistake fails in '{data['wrong_category']}', so the tests catch it.",
                ],
            )
    raise DraftRejected(reasons)
