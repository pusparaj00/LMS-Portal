"""F-29, TR-M-17: teachers edit prerequisites, a weak prerequisite is revised first, and the dashboard and the assistant
give the same recommendation (one database rule)."""
import pytest
from sqlalchemy import text

from app.concept_graph import creates_cycle
from tests.helpers import enroll
from tests.test_chat_api import say
from tests.test_feedback_api import FakeLLM, llm  # noqa: F401  (fixtures)

API = "/api/v1"


def test_a_cycle_is_found_directly_and_through_other_concepts():
    graph = {1: [], 2: [1], 3: [2]}
    assert creates_cycle(graph, 1, [3])  # 1 would need 3, which needs 2, which needs 1
    assert creates_cycle(graph, 2, [2])
    assert creates_cycle(graph, 1, [2])
    assert not creates_cycle(graph, 3, [1])  # skipping a level is fine
    assert not creates_cycle(graph, 1, [])
    assert not creates_cycle({1: [], 2: []}, 2, [1])


@pytest.fixture
def chain(client, make_user, owner):
    """A course where c builds on b and b on a, each with one coding problem."""
    _, teacher = make_user("instructor")
    course = client.post(f"{API}/courses", headers=teacher, json={"title": "Chain"}).json()["id"]
    ids = {}
    for name in ("variables", "loops", "lists"):
        ids[name] = client.post(f"{API}/courses/{course}/concepts", headers=teacher, json={"name": name}).json()["concept_id"]
    for child, parent in (("loops", "variables"), ("lists", "loops")):
        done = client.put(f"{API}/courses/{course}/concepts/{ids[child]}/prerequisites", headers=teacher,
                          json={"prerequisite_ids": [ids[parent]]})
        assert done.status_code == 200, done.text
    problems = {}
    with owner.begin() as conn:
        for name, concept in ids.items():
            pid = conn.execute(
                text(
                    "INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a)"
                    " VALUES (:c, :t, 's', 'code', 0, 1) RETURNING id"
                ),
                {"c": course, "t": f"practice {name}"},
            ).scalar_one()
            conn.execute(text("INSERT INTO problem_concepts VALUES (:p, :k, 1.0)"), {"p": pid, "k": concept})
            problems[name] = pid
    return {"course": course, "teacher": teacher, "ids": ids, "problems": problems}


def student_with(client, make_user, owner, chain, mastery):
    user_id, headers = make_user("student")
    assert enroll(client, chain["course"], headers).status_code == 200
    with owner.begin() as conn:
        for name, p in mastery.items():
            conn.execute(
                text("INSERT INTO mastery (user_id, concept_id, p_known) VALUES (:u, :c, :p)"),
                {"u": user_id, "c": chain["ids"][name], "p": p},
            )
    return user_id, headers


def dashboard(client, headers, chain):
    return client.get(f"{API}/students/me/mastery", params={"course_id": chain["course"]}, headers=headers).json()


def test_the_teacher_sees_and_sets_prerequisites_and_nobody_else_can(client, make_user, chain):
    listed = {c["name"]: c["prerequisite_ids"] for c in client.get(
        f"{API}/courses/{chain['course']}/concepts", headers=chain["teacher"]).json()}
    ids = chain["ids"]
    assert listed == {"variables": [], "loops": [ids["variables"]], "lists": [ids["loops"]]}
    path = f"{API}/courses/{chain['course']}/concepts/{ids['lists']}/prerequisites"
    _, student = make_user("student")
    _, other = make_user("instructor")
    assert client.put(path, headers=student, json={"prerequisite_ids": []}).status_code == 403
    assert client.put(path, headers=other, json={"prerequisite_ids": []}).status_code == 403
    assert client.put(path, headers=chain["teacher"], json={"prerequisite_ids": [ids["variables"], ids["loops"]]}).json()[
        "prerequisite_ids"] == [ids["variables"], ids["loops"]]
    assert client.put(path, headers=chain["teacher"], json={"prerequisite_ids": []}).json()["prerequisite_ids"] == []


def test_a_circle_a_self_link_and_a_concept_of_another_course_are_refused(client, make_user, chain, owner):
    ids, teacher, course = chain["ids"], chain["teacher"], chain["course"]
    put = lambda concept, parents: client.put(  # noqa: E731
        f"{API}/courses/{course}/concepts/{ids[concept]}/prerequisites", headers=teacher, json={"prerequisite_ids": parents})
    assert put("variables", [ids["lists"]]).status_code == 409  # variables -> lists -> loops -> variables
    assert put("loops", [ids["lists"]]).status_code == 409
    assert put("loops", [ids["loops"]]).status_code == 422
    other_course = client.post(f"{API}/courses", headers=teacher, json={"title": "Elsewhere"}).json()["id"]
    foreign = client.post(f"{API}/courses/{other_course}/concepts", headers=teacher, json={"name": "strings"}).json()
    assert put("loops", [foreign["concept_id"]]).status_code == 422
    assert put("loops", [999999]).status_code == 422
    with owner.connect() as conn:  # nothing was changed by the refused requests
        parents = conn.execute(text("SELECT parent_ids FROM concepts WHERE id = :c"), {"c": ids["loops"]}).scalar_one()
    assert parents == [ids["variables"]]


def test_a_weak_prerequisite_is_revised_before_the_concept_that_needs_it(client, make_user, owner, chain):
    _, headers = student_with(client, make_user, owner, chain, {"variables": 0.3, "loops": 0.2, "lists": 0.6})
    rec = dashboard(client, headers, chain)["recommended"]
    assert rec["problem_id"] == chain["problems"]["variables"]
    assert rec["reason"] == "variables (30%) comes before loops, which builds on it, so revise it first"


def test_a_strong_prerequisite_leaves_the_weakest_concept_as_it_was(client, make_user, owner, chain):
    _, headers = student_with(client, make_user, owner, chain, {"variables": 0.8, "loops": 0.2, "lists": 0.6})
    rec = dashboard(client, headers, chain)["recommended"]
    assert rec["problem_id"] == chain["problems"]["loops"] and rec["reason"] == "loops is your weakest area (20% mastery)"


def test_the_weakest_not_ready_prerequisite_at_any_depth_is_chosen(client, make_user, owner, chain):
    _, headers = student_with(client, make_user, owner, chain, {"variables": 0.4, "loops": 0.3, "lists": 0.1})
    rec = dashboard(client, headers, chain)["recommended"]
    assert rec["problem_id"] == chain["problems"]["loops"] and "comes before lists" in rec["reason"]


def test_a_prerequisite_with_nothing_left_to_solve_is_skipped(client, make_user, owner, chain):
    user_id, headers = student_with(client, make_user, owner, chain, {"variables": 0.3, "loops": 0.2, "lists": 0.6})
    with owner.begin() as conn:
        sid = conn.execute(
            text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'x') RETURNING id"),
            {"u": user_id, "p": chain["problems"]["variables"]},
        ).scalar_one()
        conn.execute(text("INSERT INTO run_results (submission_id, status, passed, failed) VALUES (:s, 'passed', 1, 0)"), {"s": sid})
    rec = dashboard(client, headers, chain)["recommended"]
    assert rec["problem_id"] == chain["problems"]["loops"] and "weakest area" in rec["reason"]


def test_the_assistant_and_the_dashboard_recommend_the_same_thing(client, make_user, owner, chain, llm):
    _, headers = student_with(client, make_user, owner, chain, {"variables": 0.3, "loops": 0.2, "lists": 0.6})
    llm(FakeLLM())
    reply = say(client, headers, "what should I do next", route="recommend")
    rec = dashboard(client, headers, chain)["recommended"]
    assert f'"{rec["title"]}"' in reply["reply"] and rec["reason"] in reply["reply"]
    assert f"problem:{rec['problem_id']}" in reply["tools"]


def test_a_concept_without_prerequisites_behaves_as_before(client, make_user, owner, chain):
    with owner.begin() as conn:
        conn.execute(text("UPDATE concepts SET parent_ids = '{}' WHERE course_id = :c"), {"c": chain["course"]})
    _, headers = student_with(client, make_user, owner, chain, {"variables": 0.3, "loops": 0.2, "lists": 0.6})
    assert dashboard(client, headers, chain)["recommended"]["problem_id"] == chain["problems"]["loops"]


def test_deleting_a_concept_removes_it_from_the_prerequisites_of_others(client, chain):
    ids, teacher, course = chain["ids"], chain["teacher"], chain["course"]
    lonely = client.post(f"{API}/courses/{course}/concepts", headers=teacher, json={"name": "tuples"}).json()["concept_id"]
    client.put(f"{API}/courses/{course}/concepts/{ids['lists']}/prerequisites", headers=teacher,
               json={"prerequisite_ids": [ids["loops"], lonely]})
    assert client.delete(f"{API}/courses/{course}/concepts/{lonely}", headers=teacher).status_code == 204
    listed = {c["name"]: c["prerequisite_ids"] for c in client.get(f"{API}/courses/{course}/concepts", headers=teacher).json()}
    assert listed["lists"] == [ids["loops"]]
