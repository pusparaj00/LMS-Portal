"""F-63, F-64, F-65: dashboard figures come from the caller's own rows, and ratings follow the enrolment rule."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import erasure
from app.db import get_engine, get_redis
from tests.test_erasure import erase_mastery, make_due

API = "/api/v1"
PASSWORD = "pw-12345678"


def attempt(owner, user_id, problem_id, at, passed, failed):
    with owner.begin() as conn:
        sid = conn.execute(
            text("INSERT INTO submissions (user_id, problem_id, code, created_at) VALUES (:u, :p, 'x', :t) RETURNING id"),
            {"u": user_id, "p": problem_id, "t": at},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO run_results (submission_id, status, passed, failed) VALUES (:s, :st, :p, :f)"),
            {"s": sid, "st": "passed" if failed == 0 else "failed", "p": passed, "f": failed},
        )


@pytest.fixture(scope="module")
def school(client, make_user, owner):
    """Teacher A with a course of two assignments (one past, one future) and three students; teacher B with an empty course."""
    teacher, teacher_h = make_user("instructor")
    other, other_h = make_user("instructor")
    now = datetime.now(UTC).replace(microsecond=0)
    with owner.begin() as conn:
        def course(title, instructor):
            return conn.execute(
                text("INSERT INTO courses (title, instructor_id) VALUES (:t, :i) RETURNING id"),
                {"t": title, "i": instructor},
            ).scalar_one()

        def problem(course_id, title):
            return conn.execute(
                text("INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a)"
                     " VALUES (:c, :t, 's', 'code', 0, 1) RETURNING id"),
                {"c": course_id, "t": title},
            ).scalar_one()

        def assignment(course_id, title, due, problems):
            aid = conn.execute(
                text("INSERT INTO assignments (course_id, title, due_at) VALUES (:c, :t, :d) RETURNING id"),
                {"c": course_id, "t": title, "d": due},
            ).scalar_one()
            for p in problems:
                conn.execute(text("INSERT INTO assignment_problems (assignment_id, problem_id, points) VALUES (:a, :p, 2)"),
                             {"a": aid, "p": p})
            return aid

        course_a = course("Course A", teacher)
        course_b = course("Course B", other)
        p1, p2 = problem(course_a, "P1"), problem(course_a, "P2")
        past = assignment(course_a, "Past", now - timedelta(days=1), [p1])
        future = assignment(course_a, "Future", now + timedelta(days=3), [p2])

    def enroll(headers):
        assert client.post(f"{API}/courses/{course_a}/enroll", headers=headers).status_code == 204

    full_id, full_h = make_user("student")
    half_id, half_h = make_user("student")
    none_id, none_h = make_user("student")
    outsider_id, outsider_h = make_user("student")
    for h in (full_h, half_h, none_h):
        enroll(h)
    attempt(owner, full_id, p1, now - timedelta(days=2), 4, 0)
    attempt(owner, half_id, p1, now - timedelta(days=2), 2, 2)
    attempt(owner, full_id, p2, now - timedelta(hours=1), 1, 2)  # started, a third of the tests pass
    return {
        "teacher": teacher_h, "other": other_h, "course": course_a, "other_course": course_b, "past": past,
        "future": future, "full": (full_id, full_h), "half": (half_id, half_h), "none": (none_id, none_h),
        "outsider": (outsider_id, outsider_h),
    }


def test_student_grades_are_the_students_own_scores(client, school):
    mine = client.get(f"{API}/students/me/grades", headers=school["full"][1]).json()
    assert [c["title"] for c in mine] == ["Course A"]
    past, future = mine[0]["assignments"]
    assert (past["score"], past["possible"], past["status"]) == (2.0, 2.0, "complete")
    assert future["status"] == "in_progress" and 0 < future["score"] < future["possible"]

    half = client.get(f"{API}/students/me/grades", headers=school["half"][1]).json()[0]["assignments"][0]
    assert half["score"] == 1.0 and half["status"] == "in_progress"  # one student's work never shows in another's


def test_student_stats_count_courses_progress_and_the_next_work_still_to_do(client, school):
    stats = client.get(f"{API}/students/me/stats", headers=school["full"][1]).json()
    assert stats["enrolled_courses"] == 1
    assert (stats["assignments_complete"], stats["assignments_total"]) == (1, 2)
    assert stats["average_percent"] == pytest.approx((2 + 2 / 3) / 4 * 100, abs=0.1)
    course = stats["courses"][0]
    assert course["completed"] == 1 and course["next_due_at"] is not None
    assert [u["title"] for u in stats["upcoming"]] == ["Future"]

    empty = client.get(f"{API}/students/me/stats", headers=school["outsider"][1]).json()
    assert empty["enrolled_courses"] == 0 and empty["average_percent"] is None and empty["upcoming"] == []


def test_instructor_stats_cover_only_their_own_courses(client, school):
    mine = client.get(f"{API}/instructor/stats", headers=school["teacher"]).json()
    assert mine["courses"] == 1 and mine["students"] == 3 and mine["upcoming_assignments"] == 1
    course = mine["course_stats"][0]
    assert course["students"] == 3 and course["assignments"] == 2 and course["submissions_7d"] == 3
    assert mine["upcoming"][0]["title"] == "Future" and mine["upcoming"][0]["students"] == 3

    other = client.get(f"{API}/instructor/stats", headers=school["other"]).json()
    assert other["students"] == 0 and other["upcoming_assignments"] == 0
    assert [c["title"] for c in other["course_stats"]] == ["Course B"]


def test_course_analytics_report_completion_distribution_and_each_assignment(client, school):
    url = f"{API}/courses/{school['course']}/analytics"
    data = client.get(url, headers=school["teacher"]).json()
    assert data["students"] == 3 and data["assignments"] == 2 and data["submissions_total"] == 3
    assert data["completion_rate"] == pytest.approx(1 / 6 * 100, abs=0.1)  # 1 complete of 6 student-assignment cells
    assert sum(b["students"] for b in data["distribution"]) == 3
    past = next(a for a in data["per_assignment"] if a["title"] == "Past")
    assert (past["complete"], past["in_progress"], past["missing"]) == (1, 1, 1)

    assert client.get(url, headers=school["other"]).status_code == 403  # another teacher's course
    assert client.get(url, headers=school["full"][1]).status_code == 403  # a student


def test_analytics_of_a_course_with_no_work_have_no_percentages(client, school):
    data = client.get(f"{API}/courses/{school['other_course']}/analytics", headers=school["other"]).json()
    assert data["students"] == 0 and data["completion_rate"] is None and data["average_percent"] is None
    assert [b["students"] for b in data["distribution"]] == [0, 0, 0, 0, 0]


def rate(client, school, who, course_rating=4, instructor_rating=5, review="Clear and fair"):
    return client.put(f"{API}/courses/{school['course']}/ratings", headers=school[who][1],
                      json={"course_rating": course_rating, "instructor_rating": instructor_rating, "review": review})


def test_a_student_rates_once_saving_again_replaces_and_averages_follow(client, school):
    first = rate(client, school, "full", 4, 5)
    assert first.status_code == 200, first.text
    assert first.json()["mine"]["course_rating"] == 4 and first.json()["summary"]["count"] == 1
    again = rate(client, school, "full", 2, 3, review=None).json()
    assert again["summary"]["count"] == 1 and again["mine"]["course_rating"] == 2 and again["mine"]["review"] is None
    rate(client, school, "half", 4, 5, review="  Good pace  ")
    summary = client.get(f"{API}/courses/{school['course']}/ratings", headers=school["teacher"]).json()
    assert summary["summary"] == {"count": 2, "average_course": 3.0, "average_instructor": 4.0}
    assert summary["mine"] is None and [r["review"] for r in summary["reviews"]] == ["Good pace"]
    assert all(set(r) == {"course_rating", "instructor_rating", "review", "created_at"} for r in summary["reviews"])


@pytest.mark.parametrize("change", [{"course_rating": 0}, {"instructor_rating": 6}, {"review": "x" * 1001}, {"review": "a\x00b"}])
def test_a_rating_must_be_one_to_five_with_a_review_within_limits(client, school, change):
    body = {"course_rating": 3, "instructor_rating": 3, "review": "ok", **change}
    response = client.put(f"{API}/courses/{school['course']}/ratings", headers=school["none"][1], json=body)
    assert response.status_code == 422


def test_only_enrolled_students_rate_and_only_members_read(client, school):
    assert rate(client, school, "outsider").status_code == 403
    url = f"{API}/courses/{school['course']}/ratings"
    assert client.get(url, headers=school["outsider"][1]).status_code == 403
    assert client.get(url, headers=school["other"]).status_code == 403


def test_review_text_is_stored_as_typed(client, school):
    risky = "<script>alert(1)</script>"
    assert rate(client, school, "none", review=risky).json()["mine"]["review"] == risky


def test_erasing_a_student_removes_their_rating(client, owner, school, make_user):
    user_id, headers = make_user("student")
    client.post(f"{API}/courses/{school['course']}/enroll", headers=headers)
    client.put(f"{API}/courses/{school['course']}/ratings", headers=headers,
               json={"course_rating": 1, "instructor_rating": 1, "review": "gone soon"})
    client.post(f"{API}/me/erasure", headers=headers, json={"password": PASSWORD})
    make_due(owner, user_id)
    erasure.run_due(get_engine(), get_redis(), erase_mastery)
    with owner.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ratings WHERE user_id = :u"), {"u": user_id}).scalar_one() == 0
