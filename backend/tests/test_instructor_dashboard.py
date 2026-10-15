"""F-61: the class heatmap, misconception counts and the labelled synthetic class seed."""
import pytest
from sqlalchemy import text

from app import synthetic

API = "/api/v1"


def purge_synthetic(owner):
    with owner.begin() as conn:
        ids = "SELECT id FROM users WHERE email LIKE 'synthetic-%@synthetic.local'"
        for table in ("mastery_events", "mastery", "misconception_state", "enrollments"):
            conn.execute(text(f"DELETE FROM {table} WHERE user_id IN ({ids})"))
        conn.execute(text("DELETE FROM users WHERE email LIKE 'synthetic-%@synthetic.local'"))


@pytest.fixture(scope="module")
def seeded(placement_course, owner, make_user):
    """The placement course with its own instructor; a small synthetic class is seeded through the mastery service."""
    purge_synthetic(owner)
    with owner.connect() as conn:
        instructor_id = conn.execute(
            text("SELECT instructor_id FROM courses WHERE id = :c"), {"c": placement_course["course_id"]}
        ).scalar_one()
    from app.auth import create_token

    headers = {"Authorization": f"Bearer {create_token(instructor_id, 'instructor')}"}
    summary = synthetic.seed(placement_course["course_id"], students=6)
    yield {"summary": summary, "headers": headers, "course": placement_course["course_id"]}
    purge_synthetic(owner)


def test_the_seed_creates_labelled_students_whose_mastery_came_through_the_service(seeded, owner):
    assert seeded["summary"]["students"] == 6 and seeded["summary"]["answers_applied"] > 0
    with owner.connect() as conn:
        users = conn.execute(
            text("SELECT email, role FROM users WHERE email LIKE 'synthetic-%@synthetic.local' ORDER BY email")
        ).all()
        events = conn.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE evidence_ref LIKE 'synthetic:%') FROM mastery_events e"
                " JOIN users u ON u.id = e.user_id WHERE u.email LIKE 'synthetic-%@synthetic.local'"
            )
        ).one()
    assert [u.email for u in users][:2] == ["synthetic-01@synthetic.local", "synthetic-02@synthetic.local"]
    assert {u.role for u in users} == {"student"}
    assert events[0] > 0 and events[0] >= events[1] > 0  # every mastery change is a ledger row from the service


def test_synthetic_students_cannot_log_in(client, seeded):
    response = client.post(f"{API}/auth/login", json={"email": "synthetic-01@synthetic.local", "password": "password1"})
    assert response.status_code == 401


@pytest.mark.parametrize("email", ["someone@synthetic.local", "Synthetic-99@SYNTHETIC.LOCAL"])
def test_nobody_can_register_on_the_reserved_synthetic_domain(client, email):
    response = client.post(f"{API}/auth/register", json={"email": email, "password": "long-enough-1"})
    assert response.status_code == 422 and "reserved" in response.text


@pytest.mark.parametrize(
    "email,expected",
    [("synthetic-01@synthetic.local", True), ("synthetic-120@synthetic.local", True),
     ("rating-ab12@synthetic.local", False), ("synthetic-01@synthetic.local.evil", False), ("synthetic-x@synthetic.local", False)],
)
def test_only_seeded_names_carry_the_synthetic_label(email, expected):
    assert synthetic.is_synthetic(email) is expected


def test_seeding_again_changes_nothing(seeded, owner, placement_course):
    def state():
        with owner.connect() as conn:
            return conn.execute(
                text(
                    "SELECT count(*), COALESCE(sum(p_after), 0) FROM mastery_events e JOIN users u ON u.id = e.user_id"
                    " WHERE u.email LIKE 'synthetic-%@synthetic.local'"
                )
            ).one()

    before = state()
    assert synthetic.seed(placement_course["course_id"], students=6)["answers_applied"] == 0
    assert tuple(state()) == tuple(before)


def test_the_heatmap_has_one_row_per_student_and_one_cell_per_concept(client, seeded):
    body = client.get(f"{API}/courses/{seeded['course']}/class-mastery", headers=seeded["headers"]).json()
    assert [c["name"] for c in body["concepts"]] == ["alpha", "beta", "gamma"]
    assert len(body["students"]) == 6 and all(s["synthetic"] for s in body["students"])
    assert all(len(s["mastery"]) == 3 and all(0 < c["p_known"] < 1 for c in s["mastery"]) for s in body["students"])
    for i, concept in enumerate(body["concepts"]):
        mean = sum(s["mastery"][i]["p_known"] for s in body["students"]) / 6
        assert concept["p_known"] == pytest.approx(mean)
    assert body["students"][0]["label"] == "synthetic-01"  # no email addresses in the grid


def test_students_without_evidence_sit_at_the_prior(client, seeded, make_user, owner):
    user_id, headers = make_user("student")
    assert client.post(f"{API}/courses/{seeded['course']}/enroll", headers=headers).status_code == 204
    body = client.get(f"{API}/courses/{seeded['course']}/class-mastery", headers=seeded["headers"]).json()
    newcomer = next(s for s in body["students"] if not s["synthetic"])
    assert [c["p_known"] for c in newcomer["mastery"]] == [0.5, 0.5, 0.5]


def test_misconception_counts_match_the_stored_probabilities(client, seeded, owner):
    body = client.get(f"{API}/courses/{seeded['course']}/misconceptions", headers=seeded["headers"]).json()
    assert body and all({"name", "description", "concept", "students", "mean_probability"} <= m.keys() for m in body)
    with owner.connect() as conn:
        expected = dict(
            conn.execute(
                text(
                    "SELECT m.name, count(*) FILTER (WHERE s.probability > 0.3) FROM misconceptions m"
                    " JOIN concepts c ON c.id = m.concept_id LEFT JOIN misconception_state s ON s.misconception_id = m.id"
                    " WHERE c.course_id = :c GROUP BY m.name"
                ),
                {"c": seeded["course"]},
            ).all()
        )
    assert {m["name"]: m["students"] for m in body} == expected
    assert sum(m["students"] for m in body) > 0
    assert [m["students"] for m in body] == sorted((m["students"] for m in body), reverse=True)


def test_only_the_courses_instructor_or_an_admin_can_see_the_class(client, seeded, make_user):
    url = f"{API}/courses/{seeded['course']}"
    _, student = make_user("student")
    _, other = make_user("instructor")
    _, admin = make_user("admin")
    for path in ("/class-mastery", "/misconceptions"):
        assert client.get(url + path).status_code == 401
        assert client.get(url + path, headers=student).status_code == 403
        assert client.get(url + path, headers=other).status_code == 403
        assert client.get(url + path, headers=admin).status_code == 200
        assert client.get(url + path, headers=seeded["headers"]).status_code == 200
    assert client.get(f"{API}/courses/0/class-mastery", headers=seeded["headers"]).status_code == 403
