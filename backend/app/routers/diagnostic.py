"""Cold-start placement test (F-20 to F-27, TR-A-05, TR-M-13 to TR-M-15). Sessions live in Redis, not in memory."""
import json
import random
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text

from app import ratelimit
from app.auth import Conn, CurrentUser, can_access_course
from app.consent import consented_student
from app.db import get_redis
from app.diagnostic import selection
from app.errors import sandbox_error
from app.grading import TestSpec, grade
from app.mastery import client as mastery
from app.mastery import core
from app.sandbox import SandboxUnavailable
from app.schemas import (
    ConceptMastery,
    DiagnosticAnswerRequest,
    DiagnosticAnswerResponse,
    DiagnosticItem,
    DiagnosticResult,
    DiagnosticStartRequest,
    DiagnosticStartResponse,
    OptionOut,
    SuspectedMisconception,
)

router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])
Student = Annotated[CurrentUser, Depends(consented_student)]
SESSION_TTL_SECONDS = 2 * 60 * 60
LOCK_TTL_SECONDS = 60
TOP_MISCONCEPTIONS = 3
SUSPECTED_ABOVE = 0.3  # a single tagged wrong pick takes a 0.1 prior to about 0.37
RECHECK_QUESTIONS = 4  # F-29: a short check on the concepts that are old or thinly assessed
RECHECK_AFTER_DAYS = 14
RECHECK_AFTER_SUBMISSIONS = 10


def _key(session_id: str) -> str:
    return f"diagnostic:{session_id}"


def _load_state(session_id: str, user: CurrentUser) -> dict:
    raw = get_redis().get(_key(session_id))
    state = json.loads(raw) if raw else None
    if state is None or state["user_id"] != user.id:
        raise HTTPException(404, "placement session not found or expired")
    state.setdefault("mode", "placement")  # a session started before re-checks existed
    state.setdefault("concepts", [])
    return state


def _save_state(session_id: str, state: dict) -> None:
    get_redis().set(_key(session_id), json.dumps(state), ex=SESSION_TTL_SECONDS)


def _items(conn: Connection, course_id: int) -> list[selection.Item]:
    rows = conn.execute(
        text(
            "SELECT p.id, p.kind, p.discrimination_a, p.difficulty_b, pc.concept_id, pc.weight"
            " FROM problems p JOIN problem_concepts pc ON pc.problem_id = p.id"
            " WHERE p.course_id = :c AND p.archived_at IS NULL"
            " AND NOT EXISTS (SELECT 1 FROM assignment_problems ap WHERE ap.problem_id = p.id) ORDER BY p.id"
        ),
        {"c": course_id},
    )
    by_id: dict[int, dict] = {}
    for pid, kind, a, b, concept_id, weight in rows:
        entry = by_id.setdefault(pid, {"kind": kind, "a": a, "b": b, "concepts": {}})
        entry["concepts"][concept_id] = weight
    return [
        selection.Item(pid, e["kind"], e["a"], e["b"], e["concepts"]) for pid, e in sorted(by_id.items())
    ]


def _mastery_vector(conn: Connection, user_id: int, course_id: int) -> list[ConceptMastery]:
    rows = conn.execute(
        text(
            "SELECT c.id, c.name, COALESCE(m.p_known, c.prior) AS p, e.n, e.n_eff, e.last, e.inferred"
            " FROM concepts c LEFT JOIN mastery m ON m.concept_id = c.id AND m.user_id = :u"
            " LEFT JOIN (SELECT concept_id,"
            "   count(*) FILTER (WHERE rule_id = 'bayes_update') AS n,"
            "   COALESCE(sum(weight) FILTER (WHERE rule_id = 'bayes_update'), 0) AS n_eff,"
            "   max(created_at) FILTER (WHERE rule_id = 'bayes_update') AS last,"
            "   bool_or(rule_id IN ('ability_inference', 'pooled_estimate')) AS inferred"
            "  FROM mastery_events WHERE user_id = :u GROUP BY concept_id) e ON e.concept_id = c.id"
            " WHERE c.course_id = :c ORDER BY c.id"
        ),
        {"u": user_id, "c": course_id},
    )
    return [_learner_record(r) for r in rows]


def _learner_record(r) -> ConceptMastery:
    """TR-M-16: one concept of the learner model, computed from the ledger."""
    count = r.n or 0
    status = "assessed" if count else "estimated" if r.inferred else "not assessed"
    return ConceptMastery(
        concept_id=r.id, name=r.name, p_known=r.p, status=status, evidence_count=count,
        confidence=core.confidence_label(float(r.n_eff or 0)) if count else None,
        last_assessed=r.last.isoformat() if r.last else None,
    )


def top_misconceptions(conn: Connection, user_id: int, course_id: int) -> list[SuspectedMisconception]:
    rows = conn.execute(
        text(
            "SELECT m.name, m.description, s.probability FROM misconception_state s"
            " JOIN misconceptions m ON m.id = s.misconception_id"
            " JOIN concepts c ON c.id = m.concept_id"
            " WHERE s.user_id = :u AND c.course_id = :c AND s.probability > :min"
            " ORDER BY s.probability DESC, m.name LIMIT :n"
        ),
        {"u": user_id, "c": course_id, "n": TOP_MISCONCEPTIONS, "min": SUSPECTED_ABOVE},
    )
    return [SuspectedMisconception(name=r[0], description=r[1], probability=r[2]) for r in rows]


def _item_out(conn: Connection, problem_id: int, session_id: str) -> DiagnosticItem:
    problem = conn.execute(
        text("SELECT title, statement, kind, language FROM problems WHERE id = :p"), {"p": problem_id}
    ).one()
    options = [
        OptionOut(id=r[0], text=r[1])
        for r in conn.execute(
            text("SELECT id, option_text FROM item_options WHERE problem_id = :p ORDER BY id"),
            {"p": problem_id},
        )
    ]
    random.Random(f"{session_id}:{problem_id}").shuffle(options)  # the correct answer is not always first
    return DiagnosticItem(
        problem_id=problem_id, kind=problem.kind, title=problem.title,
        statement=problem.statement, options=options, language=problem.language,
    )


def _theta(state: dict) -> float:
    return selection.eap_theta(
        [(r["a"], r["b"], r["correct"], r["evidence"]) for r in state["responses"]],
        prior_mean=_prior_mean(state),
    )


def _usable_items(conn: Connection, state: dict, user_id: int) -> list[selection.Item]:
    # a problem whose worked solution the student has seen measures nothing, so it is left out of the pool
    seen = set(
        conn.execute(
            text("SELECT problem_id FROM worked_examples_seen WHERE user_id = :u"), {"u": user_id}
        ).scalars()
    )
    wanted = set(state["concepts"]) if state["mode"] == "recheck" else None
    return [
        i for i in _items(conn, state["course_id"])
        if (i.id not in seen or i.id in state["asked"]) and (wanted is None or wanted & set(i.concepts))
    ]


def _recheck_concepts(conn: Connection, user_id: int, course_id: int) -> list[int]:
    """The concepts a re-check asks about: never assessed first, then the oldest evidence, then the least of it."""
    rows = conn.execute(
        text(
            "SELECT c.id FROM concepts c LEFT JOIN ("
            "  SELECT concept_id, max(created_at) AS last, COALESCE(sum(weight), 0) AS n_eff"
            "  FROM mastery_events WHERE user_id = :u AND rule_id = 'bayes_update' GROUP BY concept_id"
            ") e ON e.concept_id = c.id WHERE c.course_id = :c"
            " AND EXISTS (SELECT 1 FROM problem_concepts pc JOIN problems p ON p.id = pc.problem_id"
            "   WHERE pc.concept_id = c.id AND p.archived_at IS NULL)"
            " ORDER BY e.last ASC NULLS FIRST, COALESCE(e.n_eff, 0), c.id LIMIT :n"
        ),
        {"u": user_id, "c": course_id, "n": RECHECK_QUESTIONS},
    )
    return list(rows.scalars())


def recheck_offer(conn: Connection, user_id: int, course_id: int) -> tuple[bool, list[str]]:
    """Whether to offer the short re-check, and on which concepts: after two weeks, or ten submissions, since the last
    placement or re-check answers (F-29)."""
    last = conn.execute(
        text(
            "SELECT max(e.created_at) FROM mastery_events e JOIN concepts c ON c.id = e.concept_id"
            " WHERE e.user_id = :u AND c.course_id = :c AND e.evidence_ref LIKE 'diagnostic:%'"
            " AND e.rule_id = 'bayes_update'"
        ),
        {"u": user_id, "c": course_id},
    ).scalar()
    if last is None:
        return False, []
    since = conn.execute(
        text(
            "SELECT count(*) FROM submissions s JOIN problems p ON p.id = s.problem_id"
            " WHERE s.user_id = :u AND p.course_id = :c AND s.created_at > :t"
        ),
        {"u": user_id, "c": course_id, "t": last},
    ).scalar_one()
    old = conn.execute(
        text("SELECT :t < now() - make_interval(days => :d)"), {"t": last, "d": RECHECK_AFTER_DAYS}
    ).scalar_one()
    if not (old or since >= RECHECK_AFTER_SUBMISSIONS):
        return False, []
    names = conn.execute(
        text("SELECT name FROM concepts WHERE id = ANY(:ids)"), {"ids": _recheck_concepts(conn, user_id, course_id)}
    ).scalars()
    return True, [n.replace("_", " ") for n in sorted(names)]


def _prior_mean(state: dict) -> float:
    return selection.BACKGROUND_PRIOR_MEAN.get(state["background"], 0.0)


def _next_item(conn: Connection, state: dict, user_id: int) -> selection.Item | None:
    items = _usable_items(conn, state, user_id)
    given = [(r["problem_id"], r["correct"], r["evidence"]) for r in state["responses"]]
    if selection.should_stop(items, given, RECHECK_QUESTIONS if state["mode"] == "recheck" else None):
        return None
    return selection.select_next(items, given, state["seed"], _prior_mean(state))


@router.post("/start", response_model=DiagnosticStartResponse)
def start(body: DiagnosticStartRequest, user: Student, conn: Conn):
    if not can_access_course(conn, user, body.course_id):
        raise HTTPException(403, "you have no access to this course")
    if body.background is not None:
        conn.execute(
            text("UPDATE enrollments SET background = :b WHERE user_id = :u AND course_id = :c"),
            {"b": body.background, "u": user.id, "c": body.course_id},
        )
    background = body.background or conn.execute(
        text("SELECT background FROM enrollments WHERE user_id = :u AND course_id = :c"),
        {"u": user.id, "c": body.course_id},
    ).scalar()
    state = {
        "user_id": user.id, "course_id": body.course_id, "asked": [], "responses": [], "current": None,
        "background": background, "seed": secrets.token_hex(8), "mode": body.mode,
        "concepts": _recheck_concepts(conn, user.id, body.course_id) if body.mode == "recheck" else [],
    }
    session_pk = conn.execute(
        text(
            "INSERT INTO diagnostic_sessions (user_id, state_json, status)"
            " VALUES (:u, '{}', 'active') RETURNING id"
        ),
        {"u": user.id},
    ).scalar_one()
    session_id = str(session_pk)
    first = _next_item(conn, state, user.id)
    if first is None:
        raise HTTPException(422, "this course has no placement items")
    state["current"] = first.id
    _save_state(session_id, state)
    total = selection.max_questions(_usable_items(conn, state, user.id))
    shown = min(total, RECHECK_QUESTIONS) if body.mode == "recheck" else total
    return DiagnosticStartResponse(
        session_id=session_id, item_number=1, max_items=shown, item=_item_out(conn, first.id, session_id)
    )


def _grade_answer(conn: Connection, body: DiagnosticAnswerRequest, kind: str) -> tuple[bool, int | None]:
    if body.dont_know:
        return False, None
    if kind == "mcq":
        if body.option_id is None:
            raise HTTPException(422, "choose one of the options")
        row = conn.execute(
            text("SELECT is_correct FROM item_options WHERE id = :o AND problem_id = :p"),
            {"o": body.option_id, "p": body.problem_id},
        ).first()
        if row is None:
            raise HTTPException(422, "that option does not belong to this item")
        return bool(row.is_correct), body.option_id
    if body.code is None:
        raise HTTPException(422, "send your code")
    tests = [
        TestSpec(r.id, r.input, r.expected, r.hidden, r.category)
        for r in conn.execute(
            text("SELECT id, input, expected, hidden, category FROM test_cases WHERE problem_id = :p ORDER BY id"),
            {"p": body.problem_id},
        )
    ]
    try:
        language = conn.execute(
            text("SELECT language FROM problems WHERE id = :p"), {"p": body.problem_id}
        ).scalar_one()
        return grade(body.code, tests, language).status == "passed", None
    except SandboxUnavailable as exc:
        raise sandbox_error(exc) from None


@router.post("/answer", response_model=DiagnosticAnswerResponse)
def answer(body: DiagnosticAnswerRequest, user: Student, conn: Conn):
    ratelimit.check("diagnostic_answer", user.id)
    # A double click or a retry must not run the same answer twice, so one answer per session at a time.
    lock = _key(body.session_id) + ":lock"
    if not get_redis().set(lock, "1", nx=True, ex=LOCK_TTL_SECONDS):
        raise HTTPException(409, "your previous answer is still being checked")
    try:
        return _answer(body, user, conn)
    finally:
        get_redis().delete(lock)


def _answer(body: DiagnosticAnswerRequest, user: CurrentUser, conn: Connection) -> DiagnosticAnswerResponse:
    state = _load_state(body.session_id, user)
    if body.problem_id != state["current"]:
        raise HTTPException(409, "this is not the current placement item")
    # A question the teacher archived or put into an assignment since it was shown is skipped: nothing is graded or
    # recorded for it and the student is given the next one.
    item = next((i for i in _items(conn, state["course_id"]) if i.id == body.problem_id), None)
    if item is not None:
        correct, option_id = _grade_answer(conn, body, item.kind)
        confidence = body.confidence if item.kind == "mcq" and not body.dont_know else None
        evidence = core.answer_evidence_type(selection.EVIDENCE_TYPE[item.kind], body.dont_know, confidence)
        try:
            mastery.record_answer(
                user_id=user.id, problem_id=item.id, correct=correct,
                evidence_type=selection.EVIDENCE_TYPE[item.kind],
                evidence_ref=f"diagnostic:{body.session_id}:{item.id}", option_id=option_id,
                dont_know=body.dont_know, confidence=confidence,
            )
        except mastery.MasteryUnavailable:
            raise HTTPException(503, "mastery service unavailable, try again shortly") from None
        state["asked"].append(item.id)
        state["responses"].append(
            {"problem_id": item.id, "kind": item.kind, "a": item.a, "b": item.b, "correct": correct,
             "evidence": evidence}
        )
    upcoming = _next_item(conn, state, user.id)

    if upcoming is not None:
        state["current"] = upcoming.id
        _save_state(body.session_id, state)
        return DiagnosticAnswerResponse(
            session_id=body.session_id, done=False, item_number=len(state["asked"]) + 1,
            next_item=_item_out(conn, upcoming.id, body.session_id), result=None,
        )

    theta = _theta(state)
    if state["mode"] == "placement":  # a re-check only adds its answers; it does not reset what other evidence built
        try:
            mastery.record_pooled(
                user_id=user.id, course_id=state["course_id"], prior_mean=_prior_mean(state),
                evidence_ref=f"diagnostic:{body.session_id}",
            )
        except mastery.MasteryUnavailable:
            raise HTTPException(503, "mastery service unavailable, try again shortly") from None
    result = DiagnosticResult(
        mastery=_mastery_vector(conn, user.id, state["course_id"]),
        misconceptions=top_misconceptions(conn, user.id, state["course_id"]),
        ability=theta,
    )
    conn.execute(
        text("UPDATE diagnostic_sessions SET state_json = CAST(:s AS jsonb), status = 'completed' WHERE id = :id"),
        {"s": json.dumps({**state, "ability": theta}), "id": int(body.session_id)},
    )
    get_redis().delete(_key(body.session_id))
    return DiagnosticAnswerResponse(
        session_id=body.session_id, done=True, item_number=len(state["asked"]), next_item=None, result=result
    )
