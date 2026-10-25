"""F-02: an instructor can add concepts to a course, and a new concept works end to end with no other setup."""
import pytest

from tests.helpers import enroll

API = "/api/v1"


@pytest.fixture
def teacher(client, make_user):
    _, headers = make_user("instructor")
    course = client.post(f"{API}/courses", headers=headers, json={"title": "Concepts course"}).json()
    return {"headers": headers, "course": course["id"]}


def add(client, teacher, name, headers=None):
    return client.post(
        f"{API}/courses/{teacher['course']}/concepts", headers=headers or teacher["headers"], json={"name": name}
    )


def test_a_new_course_starts_empty_and_a_concept_can_be_added(client, teacher):
    url = f"{API}/courses/{teacher['course']}/concepts"
    assert client.get(url, headers=teacher["headers"]).json() == []
    created = add(client, teacher, "String formatting")
    assert created.status_code == 201 and created.json()["name"] == "string_formatting"
    assert [c["name"] for c in client.get(url, headers=teacher["headers"]).json()] == ["string_formatting"]


@pytest.mark.parametrize(
    "typed,stored", [("  Loops  ", "loops"), ("tuples and sets", "tuples_and_sets"), ("Big-O notation", "big_o_notation")]
)
def test_names_are_tidied_into_the_same_form_the_question_bank_uses(client, teacher, typed, stored):
    assert add(client, teacher, typed).json()["name"] == stored


def test_the_same_concept_twice_is_refused_and_another_course_may_reuse_the_name(client, teacher, make_user):
    assert add(client, teacher, "Loops").status_code == 201
    again = add(client, teacher, "loops")
    assert again.status_code == 409 and "already exists" in again.json()["error"]["message"]
    _, other = make_user("instructor")
    other_course = client.post(f"{API}/courses", headers=other, json={"title": "Other"}).json()["id"]
    assert client.post(f"{API}/courses/{other_course}/concepts", headers=other, json={"name": "loops"}).status_code == 201


@pytest.mark.parametrize("name", ["", "a", "x" * 61, "9lives", "drop table;", "naïve", "___"])
def test_unusable_names_are_refused(client, teacher, name):
    assert add(client, teacher, name).status_code == 422


def test_only_the_courses_instructor_can_add_concepts(client, teacher, make_user):
    _, other = make_user("instructor")
    _, student = make_user("student")
    _, admin = make_user("admin")
    assert add(client, teacher, "loops", headers=other).status_code == 403
    assert add(client, teacher, "loops", headers=student).status_code == 403
    assert add(client, teacher, "loops", headers=admin).status_code == 403
    assert client.post(f"{API}/courses/{teacher['course']}/concepts", json={"name": "loops"}).status_code == 401
    assert client.get(f"{API}/courses/{teacher['course']}/concepts", headers=teacher["headers"]).json() == []


def test_a_new_concept_can_be_used_for_a_problem_a_note_and_mastery_with_no_other_setup(client, teacher, make_user):
    concept = add(client, teacher, "Doubling").json()
    problem = client.post(f"{API}/problems", headers=teacher["headers"], json={
        "course_id": teacher["course"], "title": "Double it", "statement": "Print twice the number.",
        "difficulty_b": 0, "discrimination_a": 1, "reference_solution": "print(int(input()) * 2)\n",
        "concepts": [{"concept_id": concept["concept_id"], "name": "doubling", "weight": 1.0}],
        "test_cases": [
            {"input": "3\n", "expected": "6\n", "hidden": False, "category": "basic"},
            {"input": "0\n", "expected": "0\n", "hidden": True, "category": "zero"},
        ],
    })
    assert problem.status_code == 201, problem.text
    note = client.post(f"{API}/courses/{teacher['course']}/documents", headers=teacher["headers"],
                       json={"title": "Doubling", "concept": "doubling", "text": "## Doubling\nMultiply by 2."})
    assert note.status_code == 202

    _, student = make_user("student")
    assert enroll(client, teacher['course'], student).status_code == 200
    before = client.get(f"{API}/students/me/mastery", params={"course_id": teacher["course"]}, headers=student).json()
    assert [c["p_known"] for c in before["concepts"]] == [0.5]  # the population prior
    result = client.post(f"{API}/submissions", headers=student,
                         json={"problem_id": problem.json()["id"], "code": "print(int(input()) * 2)\n"})
    assert result.json()["status"] == "passed"
    after = client.get(f"{API}/students/me/mastery", params={"course_id": teacher["course"]}, headers=student).json()
    assert after["concepts"][0]["p_known"] > 0.5  # evidence moved it, using the default slip and guess rates


def test_a_second_problem_with_the_same_title_is_refused_and_the_first_is_kept(client, teacher):
    concept = add(client, teacher, "titles").json()

    def create(statement, reference, expected):
        return client.post(f"{API}/problems", headers=teacher["headers"], json={
            "course_id": teacher["course"], "title": "Same title", "statement": statement,
            "difficulty_b": 0, "discrimination_a": 1, "reference_solution": reference,
            "concepts": [{"concept_id": concept["concept_id"], "name": "titles", "weight": 1.0}],
            "test_cases": [
                {"input": "1\n", "expected": expected, "hidden": False, "category": "basic"},
                {"input": "1\n", "expected": expected, "hidden": True, "category": "basic"},
            ],
        })

    first = create("Print n + 1.", "print(int(input()) + 1)\n", "2\n")
    assert first.status_code == 201
    second = create("Print n * 10.", "print(int(input()) * 10)\n", "10\n")
    assert second.status_code == 409
    kept = client.get(f"{API}/problems/{first.json()['id']}", headers=teacher["headers"]).json()
    assert kept["statement"] == "Print n + 1." and kept["examples"][0]["expected"] == "2\n"
