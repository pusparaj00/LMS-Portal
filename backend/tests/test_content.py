"""F-02, F-03, TR-D-04: instructors fix and tidy their content; archiving keeps every student's history."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.feedback import hints, probe
from app.feedback.context import ExplainContext
from app.routers import courses as courses_router
from app.routers.diagnostic import _items
from tests.helpers import enroll

API = "/api/v1"
ADD_ONE = "n = int(input())\nprint(n + 1)\n"
TIMES_TWO = "n = int(input())\nprint(n * 2)\n"


def setup(client, make_user):
    """A teacher's course with one concept and two coding problems on it, and an enrolled student."""
    _, teacher = make_user("instructor")
    course = client.post(f"{API}/courses", headers=teacher, json={"title": f"Content {uuid.uuid4().hex[:6]}"}).json()
    concept = client.post(f"{API}/courses/{course['id']}/concepts", headers=teacher, json={"name": "loops"}).json()

    def problem(title, reference, expected, hidden_expected, difficulty=0.0):
        made = client.post(f"{API}/problems", headers=teacher, json={
            "course_id": course["id"], "title": title, "statement": f"{title}.", "difficulty_b": difficulty,
            "discrimination_a": 1, "concepts": [{"concept_id": concept["concept_id"], "name": "loops", "weight": 1}],
            "reference_solution": reference,
            "test_cases": [{"input": "3\n", "expected": expected, "hidden": False, "category": "basic"},
                           {"input": "10\n", "expected": hidden_expected, "hidden": True,
                            "category": "large_input"}],
        })
        assert made.status_code == 201, made.text
        return made.json()["id"]

    first = problem("Add one", ADD_ONE, "4\n", "11\n")
    second = problem("Double", TIMES_TWO, "6\n", "20\n", difficulty=-1.0)
    student_id, student = make_user("student")
    assert enroll(client, course['id'], student).status_code == 200
    return {"id": course["id"], "teacher": teacher, "concept": concept["concept_id"], "first": first,
            "second": second, "student_id": student_id, "student": student}


def edit_body(c, **changes):
    return {"course_id": c["id"], "title": "Add one", "statement": "Read n, print n + 1.", "difficulty_b": 0.5,
            "discrimination_a": 1, "concepts": [{"concept_id": c["concept"], "name": "loops", "weight": 1}],
            "reference_solution": ADD_ONE,
            "test_cases": [{"input": "1\n", "expected": "2\n", "hidden": False, "category": "basic"},
                           {"input": "41\n", "expected": "42\n", "hidden": True, "category": "large_input"}],
            **changes}


def test_a_course_can_be_renamed_archived_and_restored(client, make_user):
    c = setup(client, make_user)
    _, newcomer = make_user("student")
    path = f"{API}/courses/{c['id']}"
    assert client.patch(path, headers=c["teacher"], json={"title": "Renamed"}).json()["title"] == "Renamed"
    assert client.post(f"{path}/archive", headers=c["teacher"]).json()["archived"] is True
    assert c["id"] not in {x["id"] for x in client.get(f"{API}/courses", headers=newcomer).json()}
    assert enroll(client, c["id"], newcomer).status_code == 404  # an archived course is closed to new students
    mine = {x["id"]: x for x in client.get(f"{API}/courses", headers=c["teacher"]).json()}
    assert mine[c["id"]]["archived"] is True  # its teacher still sees it, to restore it
    assert client.post(f"{path}/restore", headers=c["teacher"]).json()["archived"] is False
    assert enroll(client, c["id"], newcomer).status_code == 200
    _, other = make_user("instructor")
    for call in (client.patch(path, headers=other, json={"title": "x"}), client.post(f"{path}/archive", headers=other),
                 client.post(f"{path}/archive", headers=c["student"])):
        assert call.status_code == 403


def test_a_problem_is_edited_through_the_same_checks_and_past_results_stay(client, make_user, owner):
    c = setup(client, make_user)
    path = f"{API}/problems/{c['first']}"
    done = client.post(f"{API}/submissions", headers=c["student"], json={"problem_id": c["first"], "code": ADD_ONE})
    assert done.json()["status"] == "passed"
    source = client.get(f"{path}/source", headers=c["teacher"]).json()
    assert source["reference_solution"] == ADD_ONE and any(t["hidden"] for t in source["test_cases"])
    assert client.get(f"{path}/source", headers=c["student"]).status_code == 403

    wrong = client.put(path, headers=c["teacher"], json=edit_body(c, reference_solution="print(0)\n"))
    assert wrong.status_code == 422 and "reference solution fails" in wrong.text
    clash = client.put(path, headers=c["teacher"], json=edit_body(c, title="Double"))
    assert clash.status_code == 409
    edited = client.put(path, headers=c["teacher"], json=edit_body(c))
    assert edited.status_code == 200 and edited.json()["statement"] == "Read n, print n + 1."
    assert edited.json()["review_status"] == "needs human review"
    detail = client.get(path, headers=c["student"]).json()
    assert detail["examples"] == [{"input": "1\n", "expected": "2\n"}]  # the hidden test stays hidden
    with owner.connect() as conn:
        kept = conn.execute(
            text("SELECT r.status, r.passed FROM submissions s JOIN run_results r ON r.submission_id = s.id"
                 " WHERE s.id = :s"), {"s": done.json()["submission_id"]},
        ).one()
    assert (kept.status, kept.passed) == ("passed", 2)

    reviewed = client.post(f"{path}/review", headers=c["teacher"])
    assert reviewed.json()["review_status"] == "reviewed"
    assert client.post(f"{path}/review", headers=c["student"]).status_code == 403
    _, other = make_user("instructor")
    assert client.put(path, headers=other, json=edit_body(c)).status_code == 404


def test_an_archived_problem_is_hidden_and_never_chosen_but_existing_assignments_keep_it(client, make_user, owner):
    c = setup(client, make_user)
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    assignment = client.post(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"], json={
        "title": "Week", "due_at": due, "problems": [{"problem_id": c["second"]}]}).json()
    assert client.post(f"{API}/problems/{c['second']}/archive", headers=c["teacher"]).json()["archived"] is True

    listed = client.get(f"{API}/problems", params={"course_id": c["id"]}, headers=c["student"]).json()["problems"]
    assert [p["id"] for p in listed] == [c["first"]]
    staff = client.get(f"{API}/problems", params={"course_id": c["id"]}, headers=c["teacher"]).json()["problems"]
    assert {p["id"]: p["archived"] for p in staff} == {c["first"]: False, c["second"]: True}
    assert client.get(f"{API}/problems/{c['second']}", headers=c["student"]).status_code == 404
    refused = client.post(f"{API}/submissions", headers=c["student"], json={"problem_id": c["second"], "code": "x"})
    assert refused.status_code == 404

    with owner.connect() as conn:
        assert c["second"] not in {i.id for i in _items(conn, c["id"])}  # placement
        context = ExplainContext(
            submission_id=0, user_id=c["student_id"], problem_id=c["first"], course_id=c["id"], problem_title="",
            statement="", code="", reference_solution=ADD_ONE, status="failed", error_type=None, stderr="",
            failed_categories=["basic"], failed_tests=[], error_concept_ids=frozenset(), concepts={},
            primary_concept_id=c["concept"],
        )
        offered = probe.select_probe(conn, context)
        assert offered is None or offered.problem_id != c["second"]  # probe
        assert hints.worked_example(conn, context).example_title is None  # worked example
    dashboard = client.get(f"{API}/students/me/mastery", params={"course_id": c["id"]}, headers=c["student"]).json()
    assert dashboard["recommended"]["problem_id"] == c["first"]  # recommendation

    kept = client.get(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"]).json()
    assert [p["problem_id"] for p in kept[0]["problems"]] == [c["second"]]
    again = client.put(f"{API}/courses/{c['id']}/assignments/{assignment['id']}", headers=c["teacher"], json={
        "title": "Week (edited)", "due_at": due, "problems": [{"problem_id": c["second"]}]})
    assert again.status_code == 200  # an assignment that already had it may keep it
    new = client.post(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"], json={
        "title": "Next", "due_at": due, "problems": [{"problem_id": c["second"]}]})
    assert new.status_code == 422  # but it cannot be set again

    assert client.post(f"{API}/problems/{c['second']}/restore", headers=c["teacher"]).json()["archived"] is False
    assert client.get(f"{API}/problems/{c['second']}", headers=c["student"]).status_code == 200


def test_a_concept_is_renamed_freely_but_deleted_only_when_unused(client, make_user, owner):
    c = setup(client, make_user)
    path = f"{API}/courses/{c['id']}/concepts"
    renamed = client.patch(f"{path}/{c['concept']}", headers=c["teacher"], json={"name": "For Loops"})
    assert renamed.json() == {"concept_id": c["concept"], "name": "for_loops"}
    tags = client.get(f"{API}/problems/{c['first']}", headers=c["teacher"]).json()["concepts"]
    assert [t["name"] for t in tags] == ["for_loops"]  # the tag follows the concept
    spare = client.post(path, headers=c["teacher"], json={"name": "spare"}).json()
    assert client.patch(f"{path}/{spare['concept_id']}", headers=c["teacher"], json={"name": "for loops"}).status_code == 409
    in_use = client.delete(f"{path}/{c['concept']}", headers=c["teacher"])
    assert in_use.status_code == 409 and "problems" in in_use.text
    assert client.delete(f"{path}/{spare['concept_id']}", headers=c["student"]).status_code == 403
    assert client.delete(f"{path}/{spare['concept_id']}", headers=c["teacher"]).status_code == 204
    assert client.delete(f"{path}/{spare['concept_id']}", headers=c["teacher"]).status_code == 404


def test_the_concept_delete_guard_covers_every_table_that_refers_to_concepts(owner):
    with owner.connect() as conn:
        referring = set(conn.execute(text(
            "SELECT conrelid::regclass::text FROM pg_constraint WHERE confrelid = 'concepts'::regclass AND contype = 'f'"
        )).scalars())
    guarded = {sql.split(" FROM ")[1].split()[0] for sql in courses_router._CONCEPT_USES.values()}
    assert referring == guarded


def test_deleted_notes_and_their_search_chunks_are_gone(client, make_user, owner):
    c = setup(client, make_user)
    path = f"{API}/courses/{c['id']}/documents"
    made = client.post(path, headers=c["teacher"], json={"title": "Loops", "text": "## Loops\nA for loop repeats."})
    document = made.json()["id"]
    with owner.begin() as conn:  # the worker may not have embedded it yet; a chunk proves deletion takes them too
        conn.execute(text("INSERT INTO chunks (document_id, text, chunk_index) VALUES (:d, 'A for loop repeats.', 0)"),
                     {"d": document})
    _, other = make_user("instructor")
    assert client.delete(f"{path}/{document}", headers=other).status_code == 403
    assert client.delete(f"{path}/{document}", headers=c["teacher"]).status_code == 204
    assert client.delete(f"{path}/{document}", headers=c["teacher"]).status_code == 404
    with owner.connect() as conn:
        left = conn.execute(text("SELECT count(*) FROM chunks WHERE document_id = :d"), {"d": document}).scalar_one()
    assert left == 0 and document not in {d["id"] for d in client.get(path, headers=c["teacher"]).json()}


def test_leaving_or_being_removed_keeps_the_students_work(client, make_user, owner):
    c = setup(client, make_user)
    client.post(f"{API}/submissions", headers=c["student"], json={"problem_id": c["first"], "code": ADD_ONE})
    due = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    client.post(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"],
                json={"title": "W", "due_at": due, "problems": [{"problem_id": c["first"]}]})
    remove = f"{API}/courses/{c['id']}/students/{c['student_id']}"
    assert client.delete(remove, headers=c["student"]).status_code == 403
    assert client.delete(remove, headers=c["teacher"]).status_code == 204
    assert client.delete(remove, headers=c["teacher"]).status_code == 404
    book = client.get(f"{API}/courses/{c['id']}/gradebook", headers=c["teacher"]).json()
    assert c["student_id"] not in {r["student_id"] for r in book["students"]}

    _, again = make_user("student")
    enroll(client, c['id'], again)
    assert client.delete(f"{API}/courses/{c['id']}/enroll", headers=again).status_code == 204
    assert c["id"] not in {x["id"] for x in client.get(f"{API}/courses", headers=again).json() if x["enrolled"]}
    with owner.connect() as conn:
        kept = conn.execute(text("SELECT count(*) FROM submissions WHERE user_id = :u"), {"u": c["student_id"]}).scalar_one()
    assert kept == 1
