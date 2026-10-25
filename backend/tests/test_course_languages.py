"""F-94, TR-L-13, TR-V-13: a Java course and a C course work like the Python course, end to end.

Each course is imported from its bank, then a student runs placement, submits right and wrong programs, asks for an
explanation (the model is replaced by a scripted fake), earns mastery, and an assignment shows in the gradebook.
"""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from app.bank_import import import_bank, load_bank
from evaluation.wrong_solutions_compiled import MISTAKES
from tests.helpers import enroll
from tests.test_feedback_api import FakeLLM, llm  # noqa: F401

API = "/api/v1"
BANK = Path(__file__).resolve().parents[2] / "data" / "bank"
if not BANK.exists():
    BANK = Path("/data/bank")
SYNTAX_WORDS = {"java": "Java could not compile", "c": "The compiler could not build"}
BROKEN = {
    "java": "public class Main { this is not java }\n",
    "c": "int main(void) { this is not c }\n",
}


@pytest.fixture(scope="module", params=["java", "c"])
def lang_course(request, client, make_user, owner):
    language = request.param
    instructor_id, instructor = make_user("instructor")
    with owner.begin() as conn:
        email = conn.execute(text("SELECT email FROM users WHERE id = :i"), {"i": instructor_id}).scalar_one()
        bank = load_bank(BANK / language)
        titles = {e["title"] for e in [*bank.problems, *bank.items]}
        made = import_bank(conn, bank, titles, email)
    problems = {
        r.title: r.id
        for r in owner.connect().execute(
            text("SELECT id, title FROM problems WHERE course_id = :c AND kind = 'code'"), {"c": made["course_id"]}
        )
    }
    references = {p["title"]: p["reference_solution"] for p in bank.problems}
    return {"language": language, "course": made["course_id"], "instructor": instructor, "problems": problems,
            "references": references, "instructor_id": instructor_id}


def student(client, make_user, lang_course):
    user_id, headers = make_user("student")
    assert enroll(client, lang_course["course"], headers).status_code == 200
    return user_id, headers


def submit(client, headers, lang_course, title, code):
    response = client.post(
        f"{API}/submissions", headers=headers, json={"problem_id": lang_course["problems"][title], "code": code}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_course_and_its_problems_carry_the_language(client, owner, lang_course):
    language = lang_course["language"]
    listed = client.get(f"{API}/courses", headers=lang_course["instructor"]).json()
    assert next(c for c in listed if c["id"] == lang_course["course"])["language"] == language
    with owner.connect() as conn:
        languages = conn.execute(
            text("SELECT DISTINCT language FROM problems WHERE course_id = :c"), {"c": lang_course["course"]}
        ).scalars().all()
    assert languages == [language]


def test_a_correct_program_passes_and_earns_mastery(client, make_user, owner, lang_course):
    user_id, headers = student(client, make_user, lang_course)
    title = "Sum of two"
    result = submit(client, headers, lang_course, title, lang_course["references"][title])
    assert result["status"] == "passed" and result["failed"] == 0
    with owner.connect() as conn:
        events = conn.execute(text("SELECT count(*) FROM mastery_events WHERE user_id = :u"), {"u": user_id}).scalar_one()
    assert events > 0


def test_a_wrong_program_fails_and_the_template_never_shows_model_text(client, make_user, owner, llm, lang_course):  # noqa: F811
    language = lang_course["language"]
    _, headers = student(client, make_user, lang_course)
    title = "Sum of two"
    old, new, _ = MISTAKES[language][title]
    result = submit(client, headers, lang_course, title, lang_course["references"][title].replace(old, new))
    assert result["status"] == "failed"
    llm(FakeLLM("SECRET-MODEL-TEXT", "SECRET-MODEL-TEXT"))
    response = client.post(f"{API}/submissions/{result['submission_id']}/explain", headers=headers)
    body = response.json()
    assert body["status"] == "fallback" and "SECRET-MODEL-TEXT" not in response.text


def test_a_program_that_does_not_compile_is_a_syntax_error_with_a_language_specific_template(
    client, make_user, llm, lang_course  # noqa: F811
):
    language = lang_course["language"]
    _, headers = student(client, make_user, lang_course)
    result = submit(client, headers, lang_course, "Sum of two", BROKEN[language])
    assert result["status"] == "error" and result["error_type"] == "syntax_error"
    llm(FakeLLM("not json", "not json"))
    body = client.post(f"{API}/submissions/{result['submission_id']}/explain", headers=headers).json()
    assert body["status"] == "fallback" and SYNTAX_WORDS[language] in body["fallback_text"]
    assert "/work" not in json.dumps(result) and "/cwork" not in json.dumps(result)


def test_placement_serves_items_in_the_course_language(client, make_user, lang_course):
    language = lang_course["language"]
    _, headers = student(client, make_user, lang_course)
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": lang_course["course"]})
    assert started.status_code == 200, started.text
    body = started.json()
    session_id, item = body["session_id"], body["item"]
    for _ in range(4):
        assert item["language"] == language
        if item["kind"] == "mcq":
            answer = {"option_id": item["options"][0]["id"]}
        else:
            answer = {"code": lang_course["references"]["Sum of two"]}
        step = client.post(
            f"{API}/diagnostic/answer", headers=headers,
            json={"session_id": session_id, "problem_id": item["problem_id"], **answer},
        )
        assert step.status_code == 200, step.text
        if step.json()["done"]:
            return
        item = step.json()["next_item"]


def test_an_assignment_is_scored_in_the_gradebook(client, make_user, owner, lang_course):
    user_id, headers = student(client, make_user, lang_course)
    title = "Sum of two"
    due = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0).isoformat()
    made = client.post(
        f"{API}/courses/{lang_course['course']}/assignments", headers=lang_course["instructor"],
        json={"title": f"{lang_course['language']} week 1", "due_at": due,
              "problems": [{"problem_id": lang_course["problems"][title], "points": 4}]},
    )
    assert made.status_code == 201, made.text
    submit(client, headers, lang_course, title, lang_course["references"][title])
    book = client.get(f"{API}/courses/{lang_course['course']}/gradebook", headers=lang_course["instructor"]).json()
    row = next(r for r in book["students"] if r["student_id"] == user_id)
    cell = next(c for c in row["cells"] if c["assignment_id"] == made.json()["id"])
    assert cell["score"] == 4


def _new_problem(lang_course, owner, reference, difficulty, title):
    with owner.connect() as conn:
        concept = conn.execute(
            text("SELECT id FROM concepts WHERE course_id = :c AND name = 'variables_io'"), {"c": lang_course["course"]}
        ).scalar_one()
    return {
        "course_id": lang_course["course"], "title": title, "statement": "Read two integers, print their sum.",
        "difficulty_b": difficulty, "discrimination_a": 1.0,
        "concepts": [{"concept_id": concept, "name": "variables_io", "weight": 1.0}],
        "reference_solution": reference,
        "test_cases": [
            {"input": "2 3\n", "expected": "5\n", "hidden": False, "category": "basic"},
            {"input": "4 5\n", "expected": "9\n", "hidden": True, "category": "basic"},
        ],
    }


def test_an_instructor_saves_a_problem_checked_in_the_course_language(client, owner, lang_course):
    language = lang_course["language"]
    saved = client.post(
        f"{API}/problems", headers=lang_course["instructor"],
        json=_new_problem(lang_course, owner, lang_course["references"]["Sum of two"], 0.0, f"{language} sum"),
    )
    assert saved.status_code == 201 and saved.json()["language"] == language, saved.text
    python_code = client.post(
        f"{API}/problems", headers=lang_course["instructor"],
        json=_new_problem(lang_course, owner, "a, b = map(int, input().split())\nprint(a + b)\n", 0.0,
                          f"{language} python sum"),
    )
    assert python_code.status_code == 422 and "reference solution fails" in python_code.text


def test_a_java_or_c_problem_needs_a_difficulty_chosen_by_the_teacher(client, owner, lang_course):
    language = lang_course["language"]
    body = _new_problem(lang_course, owner, lang_course["references"]["Sum of two"], None, f"{language} no difficulty")
    response = client.post(f"{API}/problems", headers=lang_course["instructor"], json=body)
    assert response.status_code == 422 and "only for Python" in response.text


def test_source_files_in_the_course_languages_can_be_handed_in():
    import base64

    from app.routers.work import _clean_file

    for name in ("Main.java", "main.c", "util.h"):
        cleaned, data = _clean_file(name, base64.b64encode(b"int x;\n").decode())
        assert cleaned == name and data == b"int x;\n"
