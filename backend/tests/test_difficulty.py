"""F-23, TR-D-03: a new coding problem's difficulty can be estimated from its text and concepts, and is marked so."""
from app import difficulty
from evaluation.difficulty_model import leave_one_out

API = "/api/v1"
ONE_LINER = "print(int(input()) + 1)\n"
NESTED = (
    "class Grid:\n    def __init__(self, rows):\n        self.rows = rows\n\n    def paths(self):\n"
    "        count = 0\n        for r in range(len(self.rows)):\n            for c in range(len(self.rows[r])):\n"
    "                if self.rows[r][c] == '.':\n                    while c > 0:\n                        c -= 1\n"
    "                        count += 1\n        return count\n\n\nrows = [input() for _ in range(int(input()))]\n"
    "print(Grid(rows).paths())\n"
)


def test_an_estimate_is_repeatable_bounded_and_follows_the_code():
    easy = difficulty.estimate("Read n, print n + 1.", ONE_LINER, ["loops"])
    hard = difficulty.estimate("Read a grid of rows and count the open paths using a class with methods.", NESTED,
                               ["classes", "loops"])
    assert easy == difficulty.estimate("Read n, print n + 1.", ONE_LINER, ["loops"])
    assert -2 <= easy < hard <= 2


def test_it_agrees_with_the_banks_authors_better_than_the_baselines():
    errors = leave_one_out(difficulty.bank_problems(), difficulty.RIDGE)
    assert errors["model"] < errors["concept average"] < errors["bank mean"]


def create(client, teacher, course_id, concept, **changes):
    body = {"course_id": course_id, "title": "Add one", "statement": "Read n, print n + 1.", "difficulty_b": None,
            "discrimination_a": 1, "concepts": [{"concept_id": concept, "name": "loops", "weight": 1}],
            "reference_solution": ONE_LINER,
            "test_cases": [{"input": "1\n", "expected": "2\n", "hidden": False, "category": "basic"}], **changes}
    return client.post(f"{API}/problems", headers=teacher, json=body)


def test_an_empty_difficulty_is_estimated_and_marked_and_a_chosen_one_is_kept(client, make_user):
    _, teacher = make_user("instructor")
    course = client.post(f"{API}/courses", headers=teacher, json={"title": "Estimates"}).json()["id"]
    concept = client.post(f"{API}/courses/{course}/concepts", headers=teacher, json={"name": "loops"}).json()["concept_id"]

    made = create(client, teacher, course, concept)
    assert made.status_code == 201, made.text
    assert made.json()["param_source"] == "estimated"
    assert made.json()["difficulty_b"] == difficulty.estimate("Read n, print n + 1.", ONE_LINER, ["loops"])
    source = client.get(f"{API}/problems/{made.json()['id']}/source", headers=teacher).json()
    assert source["param_source"] == "estimated"

    chosen = create(client, teacher, course, concept, title="Chosen", difficulty_b=1.0).json()
    assert (chosen["difficulty_b"], chosen["param_source"]) == (1.0, "prior")
    edited = client.put(f"{API}/problems/{chosen['id']}", headers=teacher,
                        json={**source, "title": "Chosen", "difficulty_b": None})
    assert edited.status_code == 200 and edited.json()["param_source"] == "estimated"
    assert create(client, teacher, course, concept, title="Too hard", difficulty_b=3).status_code == 422
