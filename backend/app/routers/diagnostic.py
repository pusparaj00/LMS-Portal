"""Cold-start placement test (F-20 to F-24, TR-A-05). Sessions live in Redis, not in process memory."""
import json
import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text

from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.db import get_redis
from app.diagnostic import selection
from app.grading import TestSpec, grade
from app.mastery import client as mastery
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
Student = Annotated[CurrentUser, Depends(require_role("student"))]
SESSION_TTL_SECONDS = 2 * 60 * 60
LOCK_TTL_SECONDS = 60
TOP_MISCONCEPTIONS = 3
SUSPECTED_ABOVE = 0.3  # a single tagged wrong pick takes a 0.1 prior to about 0.37


def _key(session_id: str) -> str:
    return f"diagnostic:{session_id}"


def _load_state(session_id: str, user: CurrentUser) -> dict:
    raw = get_redis().get(_key(session_id))
    state = json.loads(raw) if raw else None
    if state is None or state["user_id"] != user.id:
        raise HTTPException(404, "placement session not found or expired")
    return state


def _save_state(session_id: str, state: dict) -> None:
    get_redis().set(_key(session_id), json.dumps(state), ex=SESSION_TTL_SECONDS)


def _items(conn: Connection, course_id: int) -> list[selection.Item]:
    rows = conn.execute(
        text(
            "SELECT p.id, p.kind, p.discrimination_a, p.difficulty_b, pc.concept_id, pc.weight"
            " FROM problems p JOIN problem_concepts pc ON pc.problem_id = p.id"
            " WHERE p.course_id = :c ORDER BY p.id"
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
            "SELECT c.id, c.name, COALESCE(m.p_known, c.prior) FROM concepts c"
            " LEFT JOIN mastery m ON m.concept_id = c.id AND m.user_id = :u"
            " WHERE c.course_id = :c ORDER BY c.id"
        ),
        {"u": user_id, "c": course_id},
    )
    return [ConceptMastery(concept_id=r[0], name=r[1], p_known=r[2]) for r in rows]


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
        text("SELECT title, statement, kind FROM problems WHERE id = :p"), {"p": problem_id}
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
        statement=problem.statement, options=options,
    )


def _next_item(conn: Connection, state: dict, user_id: int) -> selection.Item | None:
    if len(state["asked"]) >= selection.MAX_ITEMS:
        return None
    vector = {c.concept_id: c.p_known for c in _mastery_vector(conn, user_id, state["course_id"])}
    if selection.uncertain_enough_to_stop(vector, len(state["asked"])):
        return None
    theta = selection.eap_theta([(r["a"], r["b"], r["correct"], r["kind"]) for r in state["responses"]])
    return selection.select_next(_items(conn, state["course_id"]), set(state["asked"]), vector, theta)


@router.post("/start", response_model=DiagnosticStartResponse)
def start(body: DiagnosticStartRequest, user: Student, conn: Conn):
    if not can_access_course(conn, user, body.course_id):
        raise HTTPException(403, "you have no access to this course")
    state = {"user_id": user.id, "course_id": body.course_id, "asked": [], "responses": [], "current": None}
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
    return DiagnosticStartResponse(
        session_id=session_id, item_number=1, max_items=selection.MAX_ITEMS,
        item=_item_out(conn, first.id, session_id),
    )


def _grade_answer(conn: Connection, body: DiagnosticAnswerRequest, kind: str) -> tuple[bool, int | None]:
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
        return grade(body.code, tests).status == "passed", None
    except SandboxUnavailable:
        raise HTTPException(503, "sandbox unavailable, try again shortly") from None


@router.post("/answer", response_model=DiagnosticAnswerResponse)
def answer(body: DiagnosticAnswerRequest, user: Student, conn: Conn):
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
    item = next(i for i in _items(conn, state["course_id"]) if i.id == body.problem_id)
    correct, option_id = _grade_answer(conn, body, item.kind)

    try:
        mastery.record_answer(
            user_id=user.id, problem_id=item.id, correct=correct,
            evidence_type=selection.EVIDENCE_TYPE[item.kind],
            evidence_ref=f"diagnostic:{body.session_id}:{item.id}", option_id=option_id,
        )
    except mastery.MasteryUnavailable:
        raise HTTPException(503, "mastery service unavailable, try again shortly") from None

    state["asked"].append(item.id)
    state["responses"].append(
        {"problem_id": item.id, "kind": item.kind, "a": item.a, "b": item.b, "correct": correct}
    )
    upcoming = _next_item(conn, state, user.id)

    if upcoming is not None:
        state["current"] = upcoming.id
        _save_state(body.session_id, state)
        return DiagnosticAnswerResponse(
            session_id=body.session_id, done=False, item_number=len(state["asked"]) + 1,
            next_item=_item_out(conn, upcoming.id, body.session_id), result=None,
        )

    theta = selection.eap_theta([(r["a"], r["b"], r["correct"], r["kind"]) for r in state["responses"]])
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
