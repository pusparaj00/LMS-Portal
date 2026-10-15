"""TR-D-07: mastery vectors and the ledger can be exported as CSV or JSON, without email addresses."""
import csv
import io

import pytest
from sqlalchemy import text

from app.routers.export import EVENT_COLUMNS, MASTERY_COLUMNS, _cell
from tests.test_instructor_dashboard import API, seeded  # noqa: F401  (fixture)


def get(client, seeded, kind, fmt=None, headers=None):
    params = {"format": fmt} if fmt else {}
    return client.get(
        f"{API}/courses/{seeded['course']}/export/{kind}", params=params, headers=headers or seeded["headers"]
    )


def db_count(owner, course, table):
    with owner.connect() as conn:
        return conn.execute(
            text(f"SELECT count(*) FROM {table} t JOIN concepts c ON c.id = t.concept_id WHERE c.course_id = :c"),
            {"c": course},
        ).scalar_one()


def test_the_mastery_csv_has_one_row_per_student_and_concept_and_no_email_addresses(client, seeded, owner):
    response = get(client, seeded, "mastery")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert list(rows[0].keys()) == MASTERY_COLUMNS
    assert len(rows) == db_count(owner, seeded["course"], "mastery") == 6 * 3  # six students, three concepts
    assert {r["synthetic"] for r in rows} == {"True"} and all(0 < float(r["p_known"]) < 1 for r in rows)
    assert "@" not in response.text  # nobody is named; the student id is the only handle


def test_the_json_export_matches_the_csv_and_the_database(client, seeded, owner):
    as_json = get(client, seeded, "mastery", "json").json()
    as_csv = list(csv.DictReader(io.StringIO(get(client, seeded, "mastery", "csv").text)))
    assert len(as_json) == len(as_csv) and set(as_json[0]) == set(MASTERY_COLUMNS)
    assert [(r["student_id"], r["concept_id"]) for r in as_json] == [
        (int(r["student_id"]), int(r["concept_id"])) for r in as_csv
    ]
    with owner.connect() as conn:
        expected = {
            (r.user_id, r.concept_id): r.p_known
            for r in conn.execute(text(
                "SELECT m.user_id, m.concept_id, m.p_known FROM mastery m JOIN concepts c ON c.id = m.concept_id"
                " WHERE c.course_id = :c"), {"c": seeded["course"]})
        }
    assert {(r["student_id"], r["concept_id"]): r["p_known"] for r in as_json} == pytest.approx(expected)


def test_the_ledger_export_lists_every_change_and_its_last_value_is_the_current_mastery(client, seeded, owner):
    response = get(client, seeded, "mastery-events", "json")
    events = response.json()
    assert response.status_code == 200 and len(events) == db_count(owner, seeded["course"], "mastery_events") > 0
    assert set(events[0]) == set(EVENT_COLUMNS)
    assert all(e["rule_id"] and e["evidence_type"] and 0 < e["p_after"] < 1 for e in events)
    assert all(e["evidence_ref"].startswith("synthetic:") for e in events)
    assert [e["event_id"] for e in events] == sorted(e["event_id"] for e in events)
    last = {(e["student_id"], e["concept_id"]): e["p_after"] for e in events}
    current = {(r["student_id"], r["concept_id"]): r["p_known"] for r in get(client, seeded, "mastery", "json").json()}
    assert last == pytest.approx(current)  # replaying the ledger ends at today's vector (TR-M-09)
    assert "@" not in get(client, seeded, "mastery-events").text


def test_the_default_format_is_csv_and_an_unknown_format_is_refused(client, seeded):
    assert get(client, seeded, "mastery-events").headers["content-type"].startswith("text/csv")
    assert get(client, seeded, "mastery", "xml").status_code == 422


def test_only_the_courses_instructor_or_an_admin_can_export(client, seeded, make_user):
    _, student = make_user("student")
    _, other = make_user("instructor")
    _, admin = make_user("admin")
    for kind in ("mastery", "mastery-events"):
        assert client.get(f"{API}/courses/{seeded['course']}/export/{kind}").status_code == 401
        assert get(client, seeded, kind, headers=student).status_code == 403
        assert get(client, seeded, kind, headers=other).status_code == 403
        assert get(client, seeded, kind, headers=admin).status_code == 200
        assert get(client, seeded, kind).status_code == 200


def test_text_that_a_spreadsheet_would_run_as_a_formula_is_marked_as_text():
    assert _cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and _cell("@SUM(A1)") == "'@SUM(A1)"
    assert _cell("loops") == "loops" and _cell(0.5) == 0.5 and _cell(-3) == -3 and _cell(None) is None
