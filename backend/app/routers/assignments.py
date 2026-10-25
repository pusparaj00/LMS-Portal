"""Assignments with due dates and the gradebook (F-04)."""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app import audit, grading_book, lti_grades, overall
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import (
    AssignmentIn,
    AssignmentOut,
    AssignmentProblemOut,
    AssignmentQuizOut,
    Gradebook,
    GradebookAssignment,
    GradebookCell,
    GradebookRow,
    GradeSendResult,
    MyScore,
    WorkIn,
)

router = APIRouter(prefix="/courses/{course_id}", tags=["assignments"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Staff = Annotated[CurrentUser, Depends(require_role("instructor", "admin"))]
Member = Annotated[CurrentUser, Depends(current_user)]


def _check(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


def _assignments(conn: Connection, course_id: int, assignment_id: int | None = None) -> list[AssignmentOut]:
    which = {"c": course_id, "a": assignment_id}
    where = "a.course_id = :c AND (CAST(:a AS integer) IS NULL OR a.id = :a)"
    out = {
        r.id: AssignmentOut(
            id=r.id, course_id=course_id, title=r.title, due_at=r.due_at, possible=0, problems=[],
            module_id=r.module_id, category_id=r.category_id,
        )
        for r in conn.execute(
            text(
                "SELECT a.id, a.title, a.due_at, a.module_id, a.category_id FROM assignments a"
                f" WHERE {where} ORDER BY a.due_at, a.id"
            ),
            which,
        )
    }
    for r in conn.execute(
        text(
            "SELECT a.id, ap.problem_id, p.title, ap.points FROM assignments a"
            " JOIN assignment_problems ap ON ap.assignment_id = a.id JOIN problems p ON p.id = ap.problem_id"
            f" WHERE {where} ORDER BY p.id"
        ),
        which,
    ):
        out[r.id].problems.append(AssignmentProblemOut(problem_id=r.problem_id, title=r.title, points=r.points))
        out[r.id].possible += r.points
    for r in conn.execute(
        text(
            "SELECT a.id, aq.quiz_id, q.title, aq.points, q.published FROM assignments a"
            " JOIN assignment_quizzes aq ON aq.assignment_id = a.id JOIN quizzes q ON q.id = aq.quiz_id"
            f" WHERE {where} ORDER BY q.id"
        ),
        which,
    ):
        out[r.id].quizzes.append(
            AssignmentQuizOut(quiz_id=r.quiz_id, title=r.title, points=r.points, published=r.published)
        )
        out[r.id].possible += r.points
    for r in conn.execute(
        text(
            "SELECT a.id, w.instructions, w.points, w.allow_file, w.allow_link, w.allow_text, w.rubric_id"
            " FROM assignments a"
            f" JOIN assignment_work w ON w.assignment_id = a.id WHERE {where}"
        ),
        which,
    ):
        out[r.id].work = WorkIn(
            instructions=r.instructions, points=r.points, allow_file=r.allow_file, allow_link=r.allow_link,
            allow_text=r.allow_text, rubric_id=r.rubric_id,
        )
        out[r.id].possible += r.points
    for r in conn.execute(
        text(
            "SELECT g.assignment_id, g.user_id FROM assignment_students g JOIN assignments a ON a.id = g.assignment_id"
            f" WHERE {where} ORDER BY g.user_id"
        ),
        which,
    ):
        out[r.assignment_id].students = [*(out[r.assignment_id].students or []), r.user_id]
    return list(out.values())


def _save_placement(conn: Connection, course_id: int, assignment_id: int, body: AssignmentIn) -> None:
    """Files the assignment under a topic of this course and records which students it is given to."""
    if body.module_id is not None and conn.execute(
        text("SELECT 1 FROM modules WHERE id = :m AND course_id = :c"), {"m": body.module_id, "c": course_id}
    ).first() is None:
        raise HTTPException(422, "that topic is not part of this course")
    wanted = sorted(set(body.students or []))
    if wanted:
        found = set(conn.execute(
            text(
                "SELECT e.user_id FROM enrollments e JOIN users u ON u.id = e.user_id"
                " WHERE e.course_id = :c AND u.role = 'student' AND e.user_id = ANY(:ids)"
            ),
            {"c": course_id, "ids": wanted},
        ).scalars())
        if found != set(wanted):
            raise HTTPException(422, "every chosen student must be in this course")
    if body.category_id is not None and conn.execute(
        text("SELECT 1 FROM grade_categories WHERE id = :g AND course_id = :c"),
        {"g": body.category_id, "c": course_id},
    ).first() is None:
        raise HTTPException(422, "that grade category is not part of this course")
    conn.execute(
        text("UPDATE assignments SET module_id = :m, category_id = :g WHERE id = :a"),
        {"m": body.module_id, "g": body.category_id, "a": assignment_id},
    )
    conn.execute(text("DELETE FROM assignment_students WHERE assignment_id = :a"), {"a": assignment_id})
    for user_id in wanted:
        conn.execute(
            text("INSERT INTO assignment_students (assignment_id, user_id) VALUES (:a, :u)"),
            {"a": assignment_id, "u": user_id},
        )


def _save_problems(conn: Connection, course_id: int, assignment_id: int, body: AssignmentIn) -> None:
    ids = [p.problem_id for p in body.problems]
    usable = set(conn.execute(
        text(
            "SELECT id FROM problems WHERE id = ANY(:ids) AND course_id = :c AND kind = 'code' AND (archived_at IS NULL"
            " OR id IN (SELECT problem_id FROM assignment_problems WHERE assignment_id = :a))"
        ),
        {"ids": ids, "c": course_id, "a": assignment_id},
    ).scalars())
    refused = [i for i in ids if i not in usable]
    if refused:
        raise HTTPException(422, f"not a live coding problem of this course: {', '.join(map(str, refused))}")
    conn.execute(text("DELETE FROM assignment_problems WHERE assignment_id = :a"), {"a": assignment_id})
    for p in body.problems:
        conn.execute(
            text("INSERT INTO assignment_problems (assignment_id, problem_id, points) VALUES (:a, :p, :w)"),
            {"a": assignment_id, "p": p.problem_id, "w": p.points},
        )


def _save_quizzes(conn: Connection, course_id: int, assignment_id: int, body: AssignmentIn) -> None:
    ids = [q.quiz_id for q in body.quizzes]
    usable = set(conn.execute(
        text("SELECT id FROM quizzes WHERE id = ANY(:ids) AND course_id = :c"), {"ids": ids, "c": course_id}
    ).scalars())
    refused = [i for i in ids if i not in usable]
    if refused:
        raise HTTPException(422, f"not a quiz of this course: {', '.join(map(str, refused))}")
    conn.execute(text("DELETE FROM assignment_quizzes WHERE assignment_id = :a"), {"a": assignment_id})
    for q in body.quizzes:
        conn.execute(
            text("INSERT INTO assignment_quizzes (assignment_id, quiz_id, points) VALUES (:a, :q, :w)"),
            {"a": assignment_id, "q": q.quiz_id, "w": q.points},
        )


def _save_work(conn: Connection, course_id: int, assignment_id: int, body: AssignmentIn) -> None:
    """Sets, changes or removes the handed-in work. Work that students have already handed in cannot be removed, and
    its points cannot drop below a score already given."""
    handed_in, top_score = conn.execute(
        text("SELECT count(*), max(score) FROM work_submissions WHERE assignment_id = :a AND "
             "(status = 'turned_in' OR body IS NOT NULL OR link IS NOT NULL OR file_name IS NOT NULL)"),
        {"a": assignment_id},
    ).one()
    if body.work is None:
        if handed_in:
            raise HTTPException(409, "students have handed in work for this assignment, so the work cannot be removed")
        conn.execute(text("DELETE FROM assignment_work WHERE assignment_id = :a"), {"a": assignment_id})
        return
    if top_score is not None and body.work.points < top_score:
        raise HTTPException(409, f"a score of {top_score:g} has been given, so the work cannot be worth fewer points")
    if body.work.rubric_id is not None:
        top = conn.execute(
            text(
                "SELECT sum(best) FROM (SELECT max(l.points) AS best FROM rubric_criteria c"
                " JOIN rubric_levels l ON l.criterion_id = c.id JOIN rubrics r ON r.id = c.rubric_id"
                " WHERE r.id = :r AND r.course_id = :c GROUP BY c.id) t"
            ),
            {"r": body.work.rubric_id, "c": course_id},
        ).scalar()
        if top is None:
            raise HTTPException(422, "that rubric is not part of this course")
        if abs(top - body.work.points) > 1e-9:
            raise HTTPException(422, f"the rubric's top score is {top:g}, so the work must be worth {top:g} points")
    conn.execute(
        text(
            "INSERT INTO assignment_work (assignment_id, instructions, points, allow_file, allow_link, allow_text,"
            " rubric_id) VALUES (:a, :i, :p, :f, :l, :t, :rb) ON CONFLICT (assignment_id) DO UPDATE SET"
            " instructions = :i, points = :p, allow_file = :f, allow_link = :l, allow_text = :t, rubric_id = :rb"
        ),
        {"a": assignment_id, "i": body.work.instructions.strip(), "p": body.work.points, "f": body.work.allow_file,
         "l": body.work.allow_link, "t": body.work.allow_text, "rb": body.work.rubric_id},
    )


def _owned(conn: Connection, course_id: int, assignment_id: int) -> None:
    if conn.execute(
        text("SELECT 1 FROM assignments WHERE id = :a AND course_id = :c"), {"a": assignment_id, "c": course_id}
    ).first() is None:
        raise HTTPException(404, "assignment not found")


def _confirm_past_due(body: AssignmentIn, current: datetime | None = None) -> None:
    """A due date that has already passed makes every student late at once; the teacher has to say that is meant (G-15).
    An edit that leaves the stored date as it is does not ask again."""
    if body.confirm_past_due or body.due_at >= datetime.now(UTC) or body.due_at == current:
        return
    raise HTTPException(
        422, "the due date has already passed, so every student would be late at once; send confirm_past_due to keep it"
    )


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(course_id: int, user: Member, conn: Conn):
    """Every assignment in the course by due date; a student also gets their own score for each."""
    _check(conn, user, course_id)
    items = _assignments(conn, course_id)
    if user.role == "student":
        # an assignment given to chosen students is invisible to the others, and nobody learns who was chosen
        items = [i for i in items if i.students is None or user.id in i.students]
        for item in items:
            item.students = None
        mine = {s.assignment_id: s for s in grading_book.scores(conn, course_id, only_student=user.id)}
        for item in items:
            s = mine.get(item.id)
            item.mine = MyScore(
                score=s.score if s else 0, with_late=s.with_late if s else 0, possible=item.possible,
                status=s.status if s else "not_started",
            )
    return items


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(course_id: int, body: AssignmentIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _confirm_past_due(body)
    assignment_id = conn.execute(
        text("INSERT INTO assignments (course_id, title, due_at) VALUES (:c, :t, :d) RETURNING id"),
        {"c": course_id, "t": body.title, "d": body.due_at},
    ).scalar_one()
    _save_problems(conn, course_id, assignment_id, body)
    _save_quizzes(conn, course_id, assignment_id, body)
    _save_work(conn, course_id, assignment_id, body)
    _save_placement(conn, course_id, assignment_id, body)
    return _assignments(conn, course_id, assignment_id)[0]


@router.put("/assignments/{assignment_id}", response_model=AssignmentOut)
def update_assignment(course_id: int, assignment_id: int, body: AssignmentIn, user: Instructor, conn: Conn):
    """Changing the problems or the due date changes every score at once: scores are computed, not stored."""
    _check(conn, user, course_id)
    _owned(conn, course_id, assignment_id)
    _confirm_past_due(body, conn.execute(
        text("SELECT due_at FROM assignments WHERE id = :a"), {"a": assignment_id}
    ).scalar_one())
    conn.execute(
        text("UPDATE assignments SET title = :t, due_at = :d WHERE id = :a"),
        {"t": body.title, "d": body.due_at, "a": assignment_id},
    )
    _save_problems(conn, course_id, assignment_id, body)
    _save_quizzes(conn, course_id, assignment_id, body)
    _save_work(conn, course_id, assignment_id, body)
    _save_placement(conn, course_id, assignment_id, body)
    return _assignments(conn, course_id, assignment_id)[0]


@router.delete("/assignments/{assignment_id}", status_code=204)
def delete_assignment(course_id: int, assignment_id: int, user: Instructor, conn: Conn):
    """Removes the assignment only; the students' submissions stay."""
    _check(conn, user, course_id)
    _owned(conn, course_id, assignment_id)
    if conn.execute(
        text("SELECT 1 FROM work_submissions WHERE assignment_id = :a LIMIT 1"), {"a": assignment_id}
    ).first():
        raise HTTPException(409, "students have worked on this assignment, so it cannot be deleted")
    conn.execute(text("DELETE FROM assignments WHERE id = :a"), {"a": assignment_id})
    return Response(status_code=204)


def gradebook(conn: Connection, course_id: int) -> Gradebook:
    items = _assignments(conn, course_id)
    rows: dict[int, GradebookRow] = {}
    overridden = {
        (r.assignment_id, r.user_id): r.reason
        for r in conn.execute(
            text(
                "SELECT o.assignment_id, o.user_id, o.reason FROM score_overrides o"
                " JOIN assignments a ON a.id = o.assignment_id WHERE a.course_id = :c"
            ),
            {"c": course_id},
        )
    }
    cats, category_of = overall.categories(conn, course_id), overall.assignment_categories(conn, course_id)
    scored = grading_book.scores(conn, course_id)
    for s in scored:
        row = rows.setdefault(s.student_id, GradebookRow(
            student_id=s.student_id, label=s.label, synthetic=s.synthetic, cells=[], total=0, total_with_late=0
        ))
        row.cells.append(GradebookCell(assignment_id=s.assignment_id, score=s.score, with_late=s.with_late,
                                       status=s.status,
                                       override_reason=overridden.get((s.assignment_id, s.student_id))))
        row.total = round(row.total + s.score, 4)
        row.total_with_late = round(row.total_with_late + s.with_late, 4)
    order = {a.id: n for n, a in enumerate(items)}  # the columns' order (by due date), not the id order of the query
    possible = {a.id: a.possible for a in items}
    for row in rows.values():
        row.cells.sort(key=lambda c: order[c.assignment_id])
        row.possible = sum(possible[c.assignment_id] for c in row.cells)
        row.overall = overall.compute(
            cats, category_of, [(c.assignment_id, c.score, possible[c.assignment_id]) for c in row.cells]
        )
    return Gradebook(
        assignments=[GradebookAssignment(id=a.id, title=a.title, due_at=a.due_at, possible=a.possible) for a in items],
        students=list(rows.values()),
        possible=sum(a.possible for a in items),
        lms_grades=lti_grades.readiness(lti_grades.link(conn, course_id)),
    )


@router.get("/gradebook", response_model=Gradebook)
def read_gradebook(course_id: int, user: Staff, conn: Conn):
    """Students by assignment: the on-time score, what late work would make it, and a status for each."""
    _check(conn, user, course_id)
    return gradebook(conn, course_id)


@router.post("/gradebook/send", response_model=GradeSendResult)
def send_grades(course_id: int, user: Instructor, conn: Conn):
    """Send every LMS student's on-time score for each assignment to the LMS the course was opened from."""
    _check(conn, user, course_id)
    try:
        result = lti_grades.send(conn, course_id, gradebook(conn, course_id))
    except lti_grades.GradeSyncError as exc:
        audit.record("lti.grades_refused", user_id=user.id, status=exc.status,
                     detail={"course_id": course_id, "reason": str(exc)[:200]})
        raise HTTPException(exc.status, str(exc)) from None
    audit.record("lti.grades_sent", user_id=user.id, status=200, detail={
        "course_id": course_id, "assignments": result.assignments, "scores_sent": result.scores_sent,
        "failures": len(result.failures),
    })
    return GradeSendResult(**vars(result))
