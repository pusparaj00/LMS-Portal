"""F-04: assignments with due dates and the gradebook. Scores come from the stored run results."""
import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import erasure
from app.db import get_engine, get_redis
from tests.test_erasure import erase_mastery, make_due

API = "/api/v1"
PASSWORD = "pw-12345678"


def iso(moment: datetime) -> str:
    return moment.isoformat()


@pytest.fixture(scope="module")
def extra(owner, course):
    """A second coding problem and a multiple-choice item in the same course, and a coding problem elsewhere."""
    with owner.begin() as conn:
        def problem(course_id, title, kind):
            return conn.execute(
                text("INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a)"
                     " VALUES (:c, :t, 's', :k, 0, 1) RETURNING id"),
                {"c": course_id, "t": title, "k": kind},
            ).scalar_one()

        other_course = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('other', :i) RETURNING id"),
            {"i": course["instructor_id"]},
        ).scalar_one()
        return {
            "second": problem(course["id"], "Second problem", "code"),
            "mcq": problem(course["id"], "Tracing item", "mcq"),
            "elsewhere": problem(other_course, "Elsewhere", "code"),
        }


def student(client, make_user, course):
    user_id, headers = make_user("student")
    assert client.post(f"{API}/courses/{course['id']}/enroll", headers=headers).status_code == 204
    return user_id, headers


def attempt(owner, user_id, problem_id, at: datetime, passed: int, failed: int) -> None:
    with owner.begin() as conn:
        sid = conn.execute(
            text("INSERT INTO submissions (user_id, problem_id, code, created_at) VALUES (:u, :p, 'x', :t) RETURNING id"),
            {"u": user_id, "p": problem_id, "t": at},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO run_results (submission_id, status, passed, failed) VALUES (:s, :st, :p, :f)"),
            {"s": sid, "st": "passed" if failed == 0 else "failed", "p": passed, "f": failed},
        )


def create(client, course, due: datetime, problems, title="Week 1"):
    return client.post(f"{API}/courses/{course['id']}/assignments", headers=course["instructor"],
                       json={"title": title, "due_at": iso(due), "problems": problems})


def cell(book, student_id, assignment_id):
    row = next(r for r in book["students"] if r["student_id"] == student_id)
    return next(c for c in row["cells"] if c["assignment_id"] == assignment_id)


def test_best_on_time_attempt_counts_late_work_is_shown_beside_it_and_each_status_is_right(
    client, make_user, owner, course, extra
):
    due = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    made = create(client, course, due, [{"problem_id": course["problem_id"], "points": 2},
                                        {"problem_id": extra["second"], "points": 1}])
    assert made.status_code == 201, made.text
    a = made.json()
    assert a["possible"] == 3 and [p["points"] for p in a["problems"]] == [2, 1]

    trier, trier_h = student(client, make_user, course)
    attempt(owner, trier, course["problem_id"], due - timedelta(hours=1), 1, 3)
    attempt(owner, trier, course["problem_id"], due, 3, 1)  # exactly at the due time: on time
    attempt(owner, trier, course["problem_id"], due + timedelta(hours=1), 4, 0)  # late
    full, _ = student(client, make_user, course)
    attempt(owner, full, course["problem_id"], due - timedelta(hours=2), 4, 0)
    attempt(owner, full, extra["second"], due - timedelta(hours=2), 2, 0)
    absent, _ = student(client, make_user, course)

    book = client.get(f"{API}/courses/{course['id']}/gradebook", headers=course["instructor"]).json()
    tried = cell(book, trier, a["id"])
    assert (tried["score"], tried["with_late"], tried["status"]) == (1.5, 2.0, "late")
    assert cell(book, full, a["id"])["status"] == "complete" and cell(book, full, a["id"])["score"] == 3
    assert (cell(book, absent, a["id"])["score"], cell(book, absent, a["id"])["status"]) == (0, "missing")
    row = next(r for r in book["students"] if r["student_id"] == trier)
    assert row["total"] == 1.5 and row["total_with_late"] == 2.0 and row["label"]

    mine = client.get(f"{API}/courses/{course['id']}/assignments", headers=trier_h).json()
    assert [m["mine"] for m in mine if m["id"] == a["id"]] == [
        {"score": 1.5, "with_late": 2.0, "possible": 3.0, "status": "late"}
    ]

    # moving the due date past the late attempt makes it count: scores are computed, not stored
    moved = client.put(f"{API}/courses/{course['id']}/assignments/{a['id']}", headers=course["instructor"],
                       json={"title": "Week 1", "due_at": iso(due + timedelta(days=2)),
                             "problems": [{"problem_id": course["problem_id"], "points": 2}]})
    assert moved.status_code == 200 and moved.json()["possible"] == 2
    book = client.get(f"{API}/courses/{course['id']}/gradebook", headers=course["instructor"]).json()
    assert cell(book, trier, a["id"])["status"] == "complete"
    assert cell(book, absent, a["id"])["status"] == "not_started"  # due tomorrow now


def test_hidden_tests_count_towards_the_score(client, make_user, course):
    a = create(client, course, datetime.now(UTC) + timedelta(days=1), [{"problem_id": course["problem_id"]}]).json()
    _, headers = student(client, make_user, course)
    visible_only = "print({'1': 2, '41': 42}.get(input(), 0))\n"  # right on the two examples, wrong on the hidden two
    result = client.post(f"{API}/submissions", headers=headers, json={"problem_id": course["problem_id"],
                                                                     "code": visible_only}).json()
    assert (result["passed"], result["failed"]) == (2, 2)
    mine = next(m for m in client.get(f"{API}/courses/{course['id']}/assignments", headers=headers).json()
                if m["id"] == a["id"])["mine"]
    assert (mine["score"], mine["status"]) == (0.5, "in_progress")


@pytest.mark.parametrize("change", [
    {"problems": [{"problem_id": "mcq"}]},
    {"problems": [{"problem_id": "elsewhere"}]},
    {"problems": [{"problem_id": "second"}, {"problem_id": "second"}]},
    {"problems": []},
    {"due_at": "2026-11-01T23:59:00"},
    {"problems": [{"problem_id": "second", "points": 0}]},
    {"title": ""},
])
def test_an_assignment_must_be_well_formed(client, course, extra, change):
    body = {"title": "Bad", "due_at": iso(datetime.now(UTC)), "problems": [{"problem_id": extra["second"]}], **change}
    body["problems"] = [{**p, "problem_id": extra.get(p["problem_id"], p["problem_id"])} for p in body["problems"]]
    response = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["instructor"], json=body)
    assert response.status_code == 422, response.text


def test_only_the_courses_teacher_manages_assignments_and_sees_the_gradebook(client, make_user, course):
    a = create(client, course, datetime.now(UTC), [{"problem_id": course["problem_id"]}]).json()
    _, enrolled = student(client, make_user, course)
    _, outsider = make_user("student")
    _, other_teacher = make_user("instructor")
    path = f"{API}/courses/{course['id']}"
    body = {"title": "x", "due_at": iso(datetime.now(UTC)), "problems": [{"problem_id": course["problem_id"]}]}
    assert client.get(f"{path}/gradebook", headers=enrolled).status_code == 403
    assert client.get(f"{path}/export/gradebook", headers=enrolled).status_code == 403
    assert client.post(f"{path}/assignments", headers=enrolled, json=body).status_code == 403
    assert client.get(f"{path}/gradebook", headers=other_teacher).status_code == 403
    assert client.post(f"{path}/assignments", headers=other_teacher, json=body).status_code == 403
    assert client.delete(f"{path}/assignments/{a['id']}", headers=other_teacher).status_code == 403
    assert client.get(f"{path}/assignments", headers=outsider).status_code == 403
    assert client.get(f"{path}/assignments").status_code == 401
    listed = client.get(f"{path}/assignments", headers=enrolled).json()
    assert all(m["mine"] is not None for m in listed)
    staff_view = client.get(f"{path}/assignments", headers=course["instructor"]).json()
    assert all(m["mine"] is None for m in staff_view)


def test_the_gradebook_download_is_formula_safe_and_audited(client, make_user, owner, course):
    a = create(client, course, datetime.now(UTC) + timedelta(days=1), [{"problem_id": course["problem_id"]}],
               title="=HYPERLINK(\"http://evil.test\")").json()
    student_id, _ = student(client, make_user, course)
    response = client.get(f"{API}/courses/{course['id']}/export/gradebook", headers=course["instructor"])
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    ours = [r for r in rows if r["student_id"] == str(student_id) and r["assignment_id"] == str(a["id"])]
    assert len(ours) == 1 and ours[0]["assignment"].startswith("'=") and ours[0]["status"] == "not_started"
    as_json = client.get(f"{API}/courses/{course['id']}/export/gradebook", params={"format": "json"},
                         headers=course["instructor"]).json()
    assert len(as_json) == len(rows)
    with owner.connect() as conn:
        kinds = conn.execute(
            text("SELECT detail->>'format' FROM audit_events WHERE event = 'export.download'"
                 " AND detail->>'kind' = 'gradebook' AND (detail->>'course_id')::int = :c ORDER BY id DESC LIMIT 2"),
            {"c": course["id"]},
        ).scalars().all()
    assert kinds == ["json", "csv"]


def test_an_erased_student_leaves_the_gradebook_and_deleting_an_assignment_keeps_submissions(
    client, make_user, owner, course
):
    a = create(client, course, datetime.now(UTC) + timedelta(days=1), [{"problem_id": course["problem_id"]}]).json()
    gone, headers = student(client, make_user, course)
    attempt(owner, gone, course["problem_id"], datetime.now(UTC), 4, 0)
    client.post(f"{API}/me/erasure", headers=headers, json={"password": PASSWORD})
    make_due(owner, gone)
    erasure.run_due(get_engine(), get_redis(), erase_mastery)
    book = client.get(f"{API}/courses/{course['id']}/gradebook", headers=course["instructor"]).json()
    assert gone not in {r["student_id"] for r in book["students"]}

    keeper, _ = student(client, make_user, course)
    attempt(owner, keeper, course["problem_id"], datetime.now(UTC), 4, 0)
    path = f"{API}/courses/{course['id']}/assignments/{a['id']}"
    assert client.delete(path, headers=course["instructor"]).status_code == 204
    assert client.delete(path, headers=course["instructor"]).status_code == 404
    with owner.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM submissions WHERE user_id = :u"), {"u": keeper}).scalar_one() == 1
