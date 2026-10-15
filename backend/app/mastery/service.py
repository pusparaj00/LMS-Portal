"""The mastery service's database logic. The only code that writes mastery and mastery_events
(TR-A-02, F-32): it runs in its own container with the lms_mastery database role."""
from dataclasses import dataclass

from sqlalchemy import Connection, text

from app.mastery import core
from app.mastery.plan import Plan, plan_submission

RULE_BAYES = "bayes_update"
RULE_PROPAGATION = "prerequisite_propagation"
DEFAULT_MISCONCEPTION_PRIOR = 0.1


@dataclass
class Change:
    concept_id: int
    concept: str
    before: float
    after: float


def _params(conn: Connection, concept_id: int, evidence_type: str) -> tuple[float, float]:
    row = conn.execute(
        text("SELECT slip, guess FROM mastery_params WHERE concept_id = :c AND evidence_type = :e"),
        {"c": concept_id, "e": evidence_type},
    ).first()
    return (row.slip, row.guess) if row else core.DEFAULT_PARAMS[evidence_type]


def _locked_mastery(conn: Connection, user_id: int, concept_id: int) -> float:
    conn.execute(
        text(
            "INSERT INTO mastery (user_id, concept_id, p_known)"
            " SELECT :u, id, prior FROM concepts WHERE id = :c ON CONFLICT DO NOTHING"
        ),
        {"u": user_id, "c": concept_id},
    )
    return conn.execute(
        text("SELECT p_known FROM mastery WHERE user_id = :u AND concept_id = :c FOR UPDATE"),
        {"u": user_id, "c": concept_id},
    ).scalar_one()


def _write_event(
    conn: Connection, *, user_id: int, concept_id: int, rule_id: str, evidence_type: str,
    weight: float, correct: bool | None, evidence_ref: str, submission_id: int | None,
    source_event_id: int | None, new_p: float, before: float,
) -> int | None:
    """Insert the ledger row and move mastery, once per (user, concept, rule, evidence)."""
    event_id = conn.execute(
        text(
            "INSERT INTO mastery_events (user_id, concept_id, p_before, p_after, evidence_type,"
            " rule_id, submission_id, evidence_ref, weight, correct, source_event_id)"
            " VALUES (:u, :c, :b, :a, :et, :r, :s, :ref, :w, :ok, :src)"
            " ON CONFLICT (user_id, concept_id, rule_id, evidence_ref) DO NOTHING RETURNING id"
        ),
        {
            "u": user_id, "c": concept_id, "b": before, "a": new_p, "et": evidence_type, "r": rule_id,
            "s": submission_id, "ref": evidence_ref, "w": weight, "ok": correct, "src": source_event_id,
        },
    ).scalar()
    if event_id is not None:
        conn.execute(
            text("UPDATE mastery SET p_known = :p, updated_at = now() WHERE user_id = :u AND concept_id = :c"),
            {"p": new_p, "u": user_id, "c": concept_id},
        )
    return event_id


def _concept_name(conn: Connection, concept_id: int) -> str:
    return conn.execute(text("SELECT name FROM concepts WHERE id = :c"), {"c": concept_id}).scalar_one()


def _apply(
    conn: Connection, user_id: int, plan: dict[int, Plan], evidence_ref: str, submission_id: int | None
) -> list[Change]:
    changes: list[Change] = []
    for concept_id in sorted(plan):
        step = plan[concept_id]
        before = _locked_mastery(conn, user_id, concept_id)
        slip, guess = _params(conn, concept_id, step.evidence_type)
        after = core.weighted_update(before, slip, guess, step.correct, step.weight)
        event_id = _write_event(
            conn, user_id=user_id, concept_id=concept_id, rule_id=RULE_BAYES,
            evidence_type=step.evidence_type, weight=step.weight, correct=step.correct,
            evidence_ref=evidence_ref, submission_id=submission_id, source_event_id=None,
            new_p=after, before=before,
        )
        if event_id is None:
            continue  # this evidence was already applied
        changes.append(Change(concept_id, _concept_name(conn, concept_id), before, after))
        changes += _propagate(conn, user_id, concept_id, event_id, before, after, evidence_ref, submission_id)
    return changes


def _propagate(
    conn: Connection, user_id: int, concept_id: int, event_id: int, before: float, after: float,
    evidence_ref: str, submission_id: int | None,
) -> list[Change]:
    if before - after < core.PROPAGATION_THRESHOLD:
        return []
    parents = conn.execute(
        text("SELECT unnest(parent_ids) FROM concepts WHERE id = :c"), {"c": concept_id}
    ).scalars().all()
    changes = []
    for parent in parents:
        parent_before = _locked_mastery(conn, user_id, parent)
        parent_after = core.propagated(parent_before, before, after)
        if parent_after is None:
            continue
        written = _write_event(
            conn, user_id=user_id, concept_id=parent, rule_id=RULE_PROPAGATION,
            evidence_type="propagation", weight=core.PROPAGATION_FRACTION, correct=None,
            evidence_ref=f"{evidence_ref}>{concept_id}", submission_id=submission_id,
            source_event_id=event_id, new_p=parent_after, before=parent_before,
        )
        if written is not None:
            changes.append(Change(parent, _concept_name(conn, parent), parent_before, parent_after))
    return changes


def record_submission(conn: Connection, submission_id: int) -> list[Change]:
    row = conn.execute(
        text(
            "SELECT s.user_id, s.problem_id, r.status, r.passed, r.error_type, r.failed_categories"
            " FROM submissions s JOIN run_results r ON r.submission_id = s.id WHERE s.id = :id"
        ),
        {"id": submission_id},
    ).first()
    if row is None:
        raise LookupError(f"no run result for submission {submission_id}")
    problem = dict(
        conn.execute(
            text("SELECT concept_id, weight FROM problem_concepts WHERE problem_id = :p"),
            {"p": row.problem_id},
        ).all()
    )
    map_rows = [
        tuple(r)
        for r in conn.execute(
            text(
                "SELECT test_category, error_type, concept_id, weight FROM evidence_concept_map"
                " WHERE concept_id IN (SELECT id FROM concepts WHERE course_id ="
                " (SELECT course_id FROM problems WHERE id = :p))"
            ),
            {"p": row.problem_id},
        )
    ]
    plan = plan_submission(
        status=row.status, passed=row.passed, error_type=row.error_type,
        failed_categories=list(row.failed_categories), problem_concepts=problem, map_rows=map_rows,
    )
    return _apply(conn, row.user_id, plan, f"submission:{submission_id}", submission_id)


BACKFILL_MIN_AGE_SECONDS = 10  # leave a fresh submission to the API's own call
BACKFILL_BATCH = 100


def backfill(conn: Connection) -> int:
    """Apply evidence for graded submissions that never reached the service (it was down).

    Safe to run any time: applying evidence is idempotent per submission.
    """
    pending = conn.execute(
        text(
            "SELECT s.id FROM submissions s JOIN run_results r ON r.submission_id = s.id"
            " WHERE NOT EXISTS (SELECT 1 FROM mastery_events e WHERE e.submission_id = s.id)"
            " AND s.created_at < now() - make_interval(secs => :age) ORDER BY s.id LIMIT :n"
        ),
        {"age": BACKFILL_MIN_AGE_SECONDS, "n": BACKFILL_BATCH},
    ).scalars().all()
    return sum(1 for submission_id in pending if record_submission(conn, submission_id))


def _update_misconception(
    conn: Connection, user_id: int, misconception_id: int, picked: bool, chose_correct: bool
) -> None:
    current = conn.execute(
        text("SELECT probability FROM misconception_state WHERE user_id = :u AND misconception_id = :m FOR UPDATE"),
        {"u": user_id, "m": misconception_id},
    ).scalar()
    probability = DEFAULT_MISCONCEPTION_PRIOR if current is None else current
    updated = core.misconception_update(probability, picked, chose_correct)
    conn.execute(
        text(
            "INSERT INTO misconception_state (user_id, misconception_id, probability)"
            " VALUES (:u, :m, :p) ON CONFLICT (user_id, misconception_id)"
            " DO UPDATE SET probability = excluded.probability, updated_at = now()"
        ),
        {"u": user_id, "m": misconception_id, "p": updated},
    )


def record_answer(
    conn: Connection, *, user_id: int, problem_id: int, correct: bool, evidence_type: str,
    evidence_ref: str, option_id: int | None,
) -> list[Change]:
    """A diagnostic or probe answer: update the item's concepts and any tagged misconceptions (TR-M-04)."""
    full_weight = evidence_type.startswith("probe")  # a probe is aimed at the weak concept: extra weight
    plan = {
        c: Plan(evidence_type, 1.0 if full_weight else min(1.0, w), correct)
        for c, w in conn.execute(
            text("SELECT concept_id, weight FROM problem_concepts WHERE problem_id = :p"),
            {"p": problem_id},
        )
    }
    picked_misconception = None
    if option_id is not None and not correct:
        picked_misconception = conn.execute(
            text(
                "SELECT m.id, m.concept_id FROM item_options o JOIN misconceptions m"
                " ON m.id = o.misconception_id WHERE o.id = :o AND o.problem_id = :p"
            ),
            {"o": option_id, "p": problem_id},
        ).first()
        if picked_misconception and picked_misconception.concept_id not in plan:
            plan[picked_misconception.concept_id] = Plan(evidence_type, 1.0, False)

    changes = _apply(conn, user_id, plan, evidence_ref, None)
    if not changes:
        return changes  # repeated request: nothing else changes either

    tagged = conn.execute(
        text(
            "SELECT DISTINCT misconception_id FROM item_options"
            " WHERE problem_id = :p AND misconception_id IS NOT NULL"
        ),
        {"p": problem_id},
    ).scalars().all()
    for misconception_id in tagged:
        picked = picked_misconception is not None and picked_misconception.id == misconception_id
        if picked or correct:
            _update_misconception(conn, user_id, misconception_id, picked, correct)
    return changes
