"""TR-A-02, TR-M-02, TR-M-04, TR-M-07, TR-M-09, F-31, F-32, F-34 against the real database."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app.mastery import core, service
from app.mastery.main import app as mastery_app


@pytest.fixture(scope="module")
def mastery_db():
    return create_engine(os.environ["MASTERY_DATABASE_URL"])


@pytest.fixture(scope="module")
def world(owner, make_user):
    """Concepts A <- C (A is C's prerequisite), B as the syntax concept, one two-concept problem."""
    instructor_id, _ = make_user("instructor")
    tag = uuid.uuid4().hex[:6]
    with owner.begin() as conn:
        course = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('mastery', :i) RETURNING id"),
            {"i": instructor_id},
        ).scalar_one()

        def concept(name, parents=()):
            return conn.execute(
                text("INSERT INTO concepts (course_id, name, parent_ids) VALUES (:c, :n, :p) RETURNING id"),
                {"c": course, "n": f"{name}_{tag}", "p": list(parents)},
            ).scalar_one()

        a, b = concept("a"), concept("b")
        c = concept("c", [a])

        def problem(title, weights):
            pid = conn.execute(
                text(
                    "INSERT INTO problems (course_id, title, statement, difficulty_b, discrimination_a)"
                    " VALUES (:c, :t, 's', 0, 1) RETURNING id"
                ),
                {"c": course, "t": title},
            ).scalar_one()
            for concept_id, w in weights.items():
                conn.execute(text("INSERT INTO problem_concepts VALUES (:p, :k, :w)"), {"p": pid, "k": concept_id, "w": w})
            return pid

        two = problem("two concepts", {a: 0.8, b: 0.2})
        child = problem("child", {c: 1.0})
        conn.execute(
            text(
                "INSERT INTO evidence_concept_map (test_category, error_type, concept_id, weight)"
                " VALUES ('only_a', '*', :a, 1.0), ('*', 'syntax_error', :b, 1.0)"
            ),
            {"a": a, "b": b},
        )
    return {"a": a, "b": b, "c": c, "two": two, "child": child, "tag": tag}


def submit(owner, make_user, problem_id, *, status, passed, failed, error_type=None, categories=()):
    user_id, _ = make_user("student")
    with owner.begin() as conn:
        sid = conn.execute(
            text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'x') RETURNING id"),
            {"u": user_id, "p": problem_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO run_results (submission_id, status, passed, failed, error_type, failed_categories)"
                " VALUES (:s, :st, :p, :f, :e, :c)"
            ),
            {"s": sid, "st": status, "p": passed, "f": failed, "e": error_type, "c": list(categories)},
        )
    return user_id, sid


def record(mastery_db, sid):
    with mastery_db.begin() as conn:
        return service.record_submission(conn, sid)


def vector(owner, user_id):
    with owner.connect() as conn:
        return dict(conn.execute(text("SELECT concept_id, p_known FROM mastery WHERE user_id = :u"), {"u": user_id}).all())


def events(owner, user_id):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT * FROM mastery_events WHERE user_id = :u ORDER BY id"), {"u": user_id}
        ).mappings().all()


def test_passing_submission_raises_every_tagged_concept_and_writes_the_ledger(owner, mastery_db, make_user, world):
    user_id, sid = submit(owner, make_user, world["two"], status="passed", passed=3, failed=0)
    changes = record(mastery_db, sid)
    assert {c.concept_id for c in changes} == {world["a"], world["b"]}
    assert all(c.after > c.before == 0.5 for c in changes)
    rows = events(owner, user_id)
    assert {r["rule_id"] for r in rows} == {"bayes_update"}
    assert all(r["evidence_ref"] == f"submission:{sid}" and r["submission_id"] == sid for r in rows)
    assert {(r["evidence_type"], r["correct"]) for r in rows} == {("all_pass", True)}
    assert vector(owner, user_id)[world["a"]] == pytest.approx(
        next(c.after for c in changes if c.concept_id == world["a"])
    )


def test_repeating_the_same_evidence_changes_nothing(owner, mastery_db, make_user, world):
    user_id, sid = submit(owner, make_user, world["two"], status="passed", passed=3, failed=0)
    record(mastery_db, sid)
    before = (vector(owner, user_id), len(events(owner, user_id)))
    assert record(mastery_db, sid) == []
    assert (vector(owner, user_id), len(events(owner, user_id))) == before


def test_a_failed_category_changes_only_its_linked_concept(owner, mastery_db, make_user, world):
    user_id, sid = submit(owner, make_user, world["two"], status="failed", passed=1, failed=1, categories=["only_a"])
    changes = record(mastery_db, sid)
    assert [c.concept_id for c in changes] == [world["a"]]
    assert changes[0].after < 0.5
    assert world["b"] not in vector(owner, user_id)


def test_an_unmapped_category_changes_all_tagged_concepts(owner, mastery_db, make_user, world):
    _, sid = submit(owner, make_user, world["two"], status="failed", passed=1, failed=1, categories=["zero"])
    assert {c.concept_id for c in record(mastery_db, sid)} == {world["a"], world["b"]}


def test_a_syntax_error_updates_only_the_syntax_concept(owner, mastery_db, make_user, world):
    _, sid = submit(
        owner, make_user, world["two"], status="error", passed=0, failed=3, error_type="syntax_error", categories=["x"]
    )
    assert [c.concept_id for c in record(mastery_db, sid)] == [world["b"]]


def test_a_partial_failure_lowers_mastery_less_than_a_total_failure(owner, mastery_db, make_user, world):
    _, partial = submit(owner, make_user, world["two"], status="failed", passed=2, failed=1, categories=["zero"])
    _, total = submit(owner, make_user, world["two"], status="failed", passed=0, failed=3, categories=["zero"])
    p = next(c.after for c in record(mastery_db, partial) if c.concept_id == world["a"])
    t = next(c.after for c in record(mastery_db, total) if c.concept_id == world["a"])
    assert t < p < 0.5


def test_a_sharp_drop_is_passed_to_the_prerequisite_and_replay_matches(owner, mastery_db, make_user, world):
    user_id, sid = submit(owner, make_user, world["child"], status="failed", passed=0, failed=3, categories=["zero"])
    changes = record(mastery_db, sid)
    assert {c.concept_id for c in changes} == {world["c"], world["a"]}
    assert vector(owner, user_id)[world["a"]] < 0.5
    rows = events(owner, user_id)
    assert [r["rule_id"] for r in rows] == ["bayes_update", "prerequisite_propagation"]
    assert rows[1]["source_event_id"] == rows[0]["id"]


def test_replaying_the_ledger_rebuilds_the_stored_vector(owner, mastery_db, make_user, world):
    user_id, first = submit(owner, make_user, world["child"], status="failed", passed=0, failed=3, categories=["z"])
    record(mastery_db, first)
    for pid, status, passed, failed in [(world["two"], "passed", 3, 0), (world["two"], "failed", 1, 2)]:
        with owner.begin() as conn:
            sid = conn.execute(
                text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'x') RETURNING id"),
                {"u": user_id, "p": pid},
            ).scalar_one()
            conn.execute(
                text("INSERT INTO run_results (submission_id, status, passed, failed, failed_categories)"
                     " VALUES (:s, :st, :p, :f, '{z}')"),
                {"s": sid, "st": status, "p": passed, "f": failed},
            )
        record(mastery_db, sid)
    rows = events(owner, user_id)
    ledger = [
        core.Event(r["id"], r["concept_id"], r["rule_id"], r["evidence_type"], r["weight"], r["correct"],
                   r["p_before"], r["p_after"], r["source_event_id"])
        for r in rows
    ]
    ids = {r["concept_id"] for r in rows}
    params = {(c, e): core.DEFAULT_PARAMS[e] for c in ids for e in core.DEFAULT_PARAMS}
    rebuilt = core.replay({c: 0.5 for c in ids}, ledger, params)
    stored = vector(owner, user_id)
    assert rebuilt == pytest.approx(stored)


def test_ledger_rows_are_append_only_for_the_mastery_role(owner, mastery_db, make_user, world):
    user_id, sid = submit(owner, make_user, world["two"], status="passed", passed=3, failed=0)
    record(mastery_db, sid)
    for statement in ("UPDATE mastery_events SET p_after = 1", "DELETE FROM mastery_events"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with mastery_db.begin() as conn:
                conn.execute(text(statement))


def test_the_http_service_needs_the_shared_token(owner, make_user, world):
    _, sid = submit(owner, make_user, world["two"], status="passed", passed=3, failed=0)
    client = TestClient(mastery_app)
    assert client.post("/evidence/submission", json={"submission_id": sid}).status_code == 401
    wrong = {"X-Service-Token": "not-the-token"}
    assert client.post("/evidence/submission", json={"submission_id": sid}, headers=wrong).status_code == 401
    right = {"X-Service-Token": os.environ["MASTERY_SERVICE_TOKEN"]}
    ok = client.post("/evidence/submission", json={"submission_id": sid}, headers=right)
    assert ok.status_code == 200 and len(ok.json()["changes"]) == 2
    assert client.post("/evidence/submission", json={"submission_id": 0}, headers=right).status_code == 404


@pytest.fixture
def item(owner, world):
    """A tracing item on concept B whose wrong options carry misconceptions on A (outside the item's concept)."""
    with owner.begin() as conn:
        pid = conn.execute(
            text(
                "INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a)"
                " SELECT course_id, :t, 's', 'mcq', 0, 1 FROM concepts WHERE id = :b RETURNING id"
            ),
            {"t": f"mcq {uuid.uuid4().hex[:6]}", "b": world["b"]},
        ).scalar_one()
        conn.execute(text("INSERT INTO problem_concepts VALUES (:p, :b, 1.0)"), {"p": pid, "b": world["b"]})
        m = conn.execute(
            text("INSERT INTO misconceptions (concept_id, name, description) VALUES (:a, :n, 'd') RETURNING id"),
            {"a": world["a"], "n": f"tagged_{uuid.uuid4().hex[:6]}"},
        ).scalar_one()
        right = conn.execute(
            text("INSERT INTO item_options (problem_id, option_text, is_correct) VALUES (:p, 'r', true) RETURNING id"),
            {"p": pid},
        ).scalar_one()
        wrong = conn.execute(
            text(
                "INSERT INTO item_options (problem_id, option_text, is_correct, misconception_id)"
                " VALUES (:p, 'w', false, :m) RETURNING id"
            ),
            {"p": pid, "m": m},
        ).scalar_one()
    return {"problem": pid, "misconception": m, "right": right, "wrong": wrong}


def answer(mastery_db, user_id, item, *, correct, option, ref="diagnostic:test:1"):
    with mastery_db.begin() as conn:
        return service.record_answer(
            conn, user_id=user_id, problem_id=item["problem"], correct=correct,
            evidence_type="diagnostic_mcq", evidence_ref=ref, option_id=option,
        )


def misconception_probability(owner, user_id, item):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT probability FROM misconception_state WHERE user_id = :u AND misconception_id = :m"),
            {"u": user_id, "m": item["misconception"]},
        ).scalar()


def test_a_tagged_wrong_option_raises_the_misconception_and_lowers_its_concept(owner, mastery_db, make_user, world, item):
    user_id, _ = make_user("student")
    changes = answer(mastery_db, user_id, item, correct=False, option=item["wrong"])
    assert {c.concept_id for c in changes} == {world["b"], world["a"]}  # the item's concept and the misconception's
    assert all(c.after < c.before for c in changes)
    assert misconception_probability(owner, user_id, item) > service.DEFAULT_MISCONCEPTION_PRIOR


def test_the_correct_option_lowers_a_misconception_and_repeats_change_nothing(owner, mastery_db, make_user, item):
    user_id, _ = make_user("student")
    answer(mastery_db, user_id, item, correct=False, option=item["wrong"], ref="diagnostic:t:1")
    raised = misconception_probability(owner, user_id, item)
    answer(mastery_db, user_id, item, correct=True, option=item["right"], ref="diagnostic:t:2")
    lowered = misconception_probability(owner, user_id, item)
    assert lowered < raised
    assert answer(mastery_db, user_id, item, correct=True, option=item["right"], ref="diagnostic:t:2") == []
    assert misconception_probability(owner, user_id, item) == lowered


def test_backfill_applies_evidence_for_submissions_that_never_reached_the_service(owner, mastery_db, make_user, world):
    user_id, sid = submit(owner, make_user, world["two"], status="passed", passed=3, failed=0)
    with owner.begin() as conn:  # old enough that the API's own call is no longer expected
        conn.execute(text("UPDATE submissions SET created_at = now() - interval '1 minute' WHERE id = :s"), {"s": sid})
    assert events(owner, user_id) == []
    with mastery_db.begin() as conn:
        assert service.backfill(conn) >= 1
    assert {r["evidence_ref"] for r in events(owner, user_id)} == {f"submission:{sid}"}
    after = vector(owner, user_id)
    with mastery_db.begin() as conn:
        service.backfill(conn)
    assert vector(owner, user_id) == after  # a second pass changes nothing


def test_backfill_leaves_fresh_submissions_to_the_api(owner, mastery_db, make_user, world):
    user_id, _ = submit(owner, make_user, world["two"], status="passed", passed=3, failed=0)
    with mastery_db.begin() as conn:
        service.backfill(conn)
    assert events(owner, user_id) == []


# The statuses sandbox/supervisor.py `_classify` can report for a failed run.
@pytest.mark.parametrize("error_type", ["runtime_error", "time_limit", "output_limit", "memory_limit"])
def test_every_failure_the_sandbox_reports_updates_mastery(owner, mastery_db, make_user, world, error_type):
    user_id, sid = submit(owner, make_user, world["two"], status="failed", passed=0, failed=3, error_type=error_type,
                          categories=["basic"])
    changes = record(mastery_db, sid)
    assert changes and all(c.after < c.before for c in changes)
    assert {e["evidence_type"] for e in events(owner, user_id)} == {error_type}


def test_backfill_skips_a_submission_it_cannot_apply_and_still_applies_the_rest(owner, mastery_db, make_user, world):
    _, broken = submit(owner, make_user, world["two"], status="failed", passed=0, failed=1, error_type="unknown_status")
    fixable_user, fixable = submit(owner, make_user, world["two"], status="passed", passed=3, failed=0)
    with owner.begin() as conn:
        conn.execute(
            text("UPDATE submissions SET created_at = now() - interval '1 minute' WHERE id = ANY(:ids)"),
            {"ids": [broken, fixable]},
        )
    with mastery_db.begin() as conn:
        service.backfill(conn)
    assert events(owner, fixable_user)
    with owner.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mastery_events WHERE submission_id = :s"), {"s": broken}).scalar() == 0
    with owner.begin() as conn:  # leave nothing for the running service's own backfill to trip over
        conn.execute(text("DELETE FROM run_results WHERE submission_id = :s"), {"s": broken})
        conn.execute(text("DELETE FROM submissions WHERE id = :s"), {"s": broken})


def test_the_ledger_sentence_joins_the_error_and_the_failed_categories():
    from types import SimpleNamespace

    from app.routers.students import _explain

    row = SimpleNamespace(rule_id="bayes_update", submission_id=7, problem_id=1, evidence_type="syntax_error",
                          run_error_type="syntax_error", failed_categories=["basic", "edge"])
    assert _explain(row, {1: "Add one"}) == (
        "Submission #7 to 'Add one' stopped with a syntax error and failed tests in: basic, edge."
    )
