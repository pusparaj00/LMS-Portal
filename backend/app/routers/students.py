"""Student dashboard and the 'why did my mastery change' view (F-34, F-60). Read-only."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text

from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.routers.diagnostic import _mastery_vector, top_misconceptions
from app.schemas import Dashboard, LedgerEntry, RecentSubmission, RecommendedProblem

router = APIRouter(prefix="/students/me", tags=["students"])
Student = Annotated[CurrentUser, Depends(require_role("student"))]
RECENT_SUBMISSIONS = 10
HISTORY_LIMIT = 50


def _recommend(conn: Connection, user_id: int, course_id: int, concepts) -> RecommendedProblem | None:
    """The easiest unsolved coding problem on the weakest concept that still has one."""
    for concept in sorted(concepts, key=lambda c: c.p_known):
        row = conn.execute(
            text(
                "SELECT p.id, p.title FROM problems p"
                " JOIN problem_concepts pc ON pc.problem_id = p.id AND pc.concept_id = :c"
                " WHERE p.kind = 'code' AND p.course_id = :course AND p.archived_at IS NULL AND NOT EXISTS ("
                "   SELECT 1 FROM submissions s JOIN run_results r ON r.submission_id = s.id"
                "   WHERE s.problem_id = p.id AND s.user_id = :u AND r.status = 'passed')"
                " ORDER BY p.difficulty_b, p.id LIMIT 1"
            ),
            {"c": concept.concept_id, "course": course_id, "u": user_id},
        ).first()
        if row:
            reason = f"{concept.name} is your weakest area ({round(concept.p_known * 100)}% mastery)"
            return RecommendedProblem(problem_id=row.id, title=row.title, reason=reason)
    return None


@router.get("/mastery", response_model=Dashboard)
def dashboard(course_id: int, user: Student, conn: Conn):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")
    concepts = _mastery_vector(conn, user.id, course_id)
    recent = conn.execute(
        text(
            "SELECT s.id, s.problem_id, p.title, r.status, r.passed, r.failed, s.created_at"
            " FROM submissions s JOIN problems p ON p.id = s.problem_id"
            " JOIN run_results r ON r.submission_id = s.id"
            " WHERE s.user_id = :u AND p.course_id = :c ORDER BY s.id DESC LIMIT :n"
        ),
        {"u": user.id, "c": course_id, "n": RECENT_SUBMISSIONS},
    )
    completed = conn.execute(
        text(
            "SELECT 1 FROM diagnostic_sessions WHERE user_id = :u AND status = 'completed'"
            " AND state_json->>'course_id' = :c LIMIT 1"
        ),
        {"u": user.id, "c": str(course_id)},
    ).first()
    return Dashboard(
        concepts=concepts,
        misconceptions=top_misconceptions(conn, user.id, course_id),
        recent_submissions=[
            RecentSubmission(
                submission_id=r[0], problem_id=r[1], problem_title=r[2], status=r[3],
                passed=r[4], failed=r[5], created_at=r[6].isoformat(),
            )
            for r in recent
        ],
        recommended=_recommend(conn, user.id, course_id, concepts),
        placement_completed=completed is not None,
    )


def _explain(row, titles: dict[int, str]) -> str:
    if row.rule_id == "prerequisite_propagation":
        return "A concept that builds on this one dropped sharply, so part of the drop was passed back."
    if row.submission_id is not None:
        title = titles.get(row.problem_id, "a problem")
        if row.evidence_type == "all_pass":
            return f"Submission #{row.submission_id} to '{title}' passed every test."
        parts = []
        if row.run_error_type:
            parts.append(f"stopped with a {row.run_error_type.replace('_', ' ')}")
        if row.failed_categories:
            parts.append("failed tests in: " + ", ".join(row.failed_categories))
        return f"Submission #{row.submission_id} to '{title}' " + (" and ".join(parts) or "failed") + "."
    title = titles.get(row.diagnostic_problem_id)
    outcome = "correct" if row.correct else "incorrect"
    return f"Placement answer to '{title or 'an item'}' was {outcome}."


@router.get("/mastery/{concept_id}/history", response_model=list[LedgerEntry])
def history(concept_id: int, user: Student, conn: Conn):
    """Every change to one concept, with the test, error and rule behind it (F-34)."""
    course = conn.execute(
        text("SELECT course_id FROM concepts WHERE id = :c"), {"c": concept_id}
    ).scalar()
    if course is None or not can_access_course(conn, user, course):
        raise HTTPException(404, "concept not found")
    rows = conn.execute(
        text(
            "SELECT e.created_at, c.name AS concept, e.p_before, e.p_after, e.evidence_type, e.rule_id,"
            " e.submission_id, e.correct, s.problem_id, r.error_type AS run_error_type,"
            " COALESCE(r.failed_categories, '{}') AS failed_categories,"
            " CASE WHEN e.evidence_ref LIKE 'diagnostic:%'"
            "   THEN substring(e.evidence_ref FROM '^diagnostic:[^:]*:([0-9]+)')::int END"
            " AS diagnostic_problem_id"
            " FROM mastery_events e JOIN concepts c ON c.id = e.concept_id"
            " LEFT JOIN submissions s ON s.id = e.submission_id"
            " LEFT JOIN run_results r ON r.submission_id = e.submission_id"
            " WHERE e.user_id = :u AND e.concept_id = :c ORDER BY e.id DESC LIMIT :n"
        ),
        {"u": user.id, "c": concept_id, "n": HISTORY_LIMIT},
    ).all()
    problem_ids = {x for r in rows for x in (r.problem_id, r.diagnostic_problem_id) if x}
    titles = {
        r[0]: r[1]
        for r in conn.execute(
            text("SELECT id, title FROM problems WHERE id = ANY(:ids)"), {"ids": list(problem_ids)}
        )
    }
    return [
        LedgerEntry(
            created_at=r.created_at.isoformat(), concept=r.concept, p_before=r.p_before,
            p_after=r.p_after, evidence_type=r.evidence_type, rule_id=r.rule_id,
            explanation=_explain(r, titles), submission_id=r.submission_id,
        )
        for r in rows
    ]
