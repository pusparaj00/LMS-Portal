"""Quizzes (F-71, F-72): the instructor writes them, students take them, the server grades them.

The right answers leave the database only for staff, and for a student only in the review of an attempt the instructor
allowed (`show_answers`) once every assignment holding the quiz is past due. A question is all-or-nothing: a choice
question is right when the chosen set equals the right set, a short answer when it matches an accepted answer after
trimming, collapsing spaces and ignoring case. The questions of a quiz that has attempts are locked, because every
stored attempt was graded against them.
"""
import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import (
    AnswerIn,
    AttemptIn,
    AttemptOut,
    AttemptRow,
    MyAttempts,
    QuestionIn,
    QuestionOut,
    QuizIn,
    QuizOut,
    QuizSummary,
    ReviewItem,
)

router = APIRouter(prefix="/courses/{course_id}/quizzes", tags=["quizzes"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Student = Annotated[CurrentUser, Depends(require_role("student"))]
Member = Annotated[CurrentUser, Depends(current_user)]

_LIST = """
SELECT q.id, q.title, q.max_attempts, q.show_answers, q.published,
       (SELECT count(*) FROM quiz_questions k WHERE k.quiz_id = q.id) AS questions,
       (SELECT count(*) FROM assignment_quizzes aq WHERE aq.quiz_id = q.id) AS in_assignments,
       (SELECT count(*) FROM quiz_attempts a WHERE a.quiz_id = q.id AND a.user_id = :u) AS used,
       (SELECT max(a.fraction) FROM quiz_attempts a WHERE a.quiz_id = q.id AND a.user_id = :u) AS best
FROM quizzes q WHERE q.course_id = :c AND (CAST(:only AS integer) IS NULL OR q.id = :only)
  AND (NOT :students_only OR q.published) ORDER BY q.id
"""


def _check(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


def _summaries(conn: Connection, user: CurrentUser, course_id: int, only: int | None = None) -> list[QuizSummary]:
    student = user.role == "student"
    rows = conn.execute(
        text(_LIST), {"c": course_id, "u": user.id, "only": only, "students_only": student}
    ).all()
    return [
        QuizSummary(
            id=r.id, title=r.title, max_attempts=r.max_attempts, show_answers=r.show_answers, published=r.published,
            questions=r.questions, in_assignments=r.in_assignments,
            attempts_used=r.used if student else None, best_fraction=r.best if student else None,
        )
        for r in rows
    ]


def _one(conn: Connection, user: CurrentUser, course_id: int, quiz_id: int) -> QuizSummary:
    found = _summaries(conn, user, course_id, quiz_id)
    if not found:  # an unpublished quiz does not exist for a student
        raise HTTPException(404, "quiz not found")
    return found[0]


def _questions(conn: Connection, quiz_id: int) -> list:
    return conn.execute(
        text("SELECT id, kind, prompt, options, correct, weight FROM quiz_questions WHERE quiz_id = :q"
             " ORDER BY position, id"),
        {"q": quiz_id},
    ).all()


def _out(row, staff: bool) -> QuestionOut:
    return QuestionOut(
        id=row.id, kind=row.kind, prompt=row.prompt, options=row.options, weight=row.weight,
        correct_choices=row.correct if staff and row.kind != "short" else None,
        accepted=row.correct if staff and row.kind == "short" else None,
    )


def _stored_correct(q: QuestionIn) -> list:
    return [a.strip() for a in q.accepted if a.strip()] if q.kind == "short" else q.correct_choices


def _save_questions(conn: Connection, quiz_id: int, questions: list[QuestionIn]) -> None:
    conn.execute(text("DELETE FROM quiz_questions WHERE quiz_id = :q"), {"q": quiz_id})
    for position, q in enumerate(questions):
        conn.execute(
            text(
                "INSERT INTO quiz_questions (quiz_id, position, kind, prompt, options, correct, weight)"
                " VALUES (:q, :p, :k, :t, CAST(:o AS jsonb), CAST(:c AS jsonb), :w)"
            ),
            {"q": quiz_id, "p": position, "k": q.kind, "t": q.prompt, "o": json.dumps(q.options),
             "c": json.dumps(_stored_correct(q)), "w": q.weight},
        )


def _same_questions(stored: list, new: list[QuestionIn]) -> bool:
    if len(stored) != len(new):
        return False
    return all(
        (s.kind, s.prompt, s.options, s.correct, s.weight)
        == (q.kind, q.prompt, q.options, _stored_correct(q), q.weight)
        for s, q in zip(stored, new, strict=True)
    )


def _attempt_count(conn: Connection, quiz_id: int) -> int:
    return conn.execute(text("SELECT count(*) FROM quiz_attempts WHERE quiz_id = :q"), {"q": quiz_id}).scalar_one()


def _normal(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _is_right(question, answer: AnswerIn | None) -> bool:
    if answer is None:
        return False
    if question.kind == "short":
        given = _normal(answer.text or "")
        return bool(given) and given in {_normal(a) for a in question.correct}
    return len(set(answer.choices)) == len(answer.choices) and set(answer.choices) == set(question.correct)


def grade(questions: list, answers: list[AnswerIn]) -> tuple[float, float, list[ReviewItem]]:
    """(earned, possible, per-question result) for the answers given; a question left out is wrong."""
    by_question = {a.question_id: a for a in answers}
    earned = possible = 0.0
    review = []
    for q in questions:
        right = _is_right(q, by_question.get(q.id))
        possible += q.weight
        earned += q.weight if right else 0
        review.append(ReviewItem(
            question_id=q.id, correct=right,
            correct_choices=q.correct if q.kind != "short" else None,
            accepted=q.correct if q.kind == "short" else None,
        ))
    return earned, possible, review


def _review_open(conn: Connection, quiz_id: int) -> bool:
    """The instructor turned review on and no assignment holding the quiz is still open."""
    return conn.execute(
        text(
            "SELECT q.show_answers AND NOT EXISTS (SELECT 1 FROM assignment_quizzes aq"
            " JOIN assignments a ON a.id = aq.assignment_id WHERE aq.quiz_id = q.id AND a.due_at > now())"
            " FROM quizzes q WHERE q.id = :q"
        ),
        {"q": quiz_id},
    ).scalar_one()


@router.get("", response_model=list[QuizSummary])
def list_quizzes(course_id: int, user: Member, conn: Conn):
    _check(conn, user, course_id)
    return _summaries(conn, user, course_id)


@router.post("", response_model=QuizOut, status_code=201)
def create_quiz(course_id: int, body: QuizIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    quiz_id = conn.execute(
        text(
            "INSERT INTO quizzes (course_id, title, max_attempts, show_answers, published)"
            " VALUES (:c, :t, :m, :s, :p) RETURNING id"
        ),
        {"c": course_id, "t": body.title, "m": body.max_attempts, "s": body.show_answers, "p": body.published},
    ).scalar_one()
    _save_questions(conn, quiz_id, body.questions)
    return _read(conn, user, course_id, quiz_id)


def _read(conn: Connection, user: CurrentUser, course_id: int, quiz_id: int) -> QuizOut:
    summary = _one(conn, user, course_id, quiz_id)
    staff = user.role != "student"
    return QuizOut(**summary.model_dump(), question_list=[_out(q, staff) for q in _questions(conn, quiz_id)])


@router.get("/{quiz_id}", response_model=QuizOut)
def read_quiz(course_id: int, quiz_id: int, user: Member, conn: Conn):
    """Staff get the right answers; a student gets the questions only."""
    _check(conn, user, course_id)
    return _read(conn, user, course_id, quiz_id)


@router.put("/{quiz_id}", response_model=QuizOut)
def update_quiz(course_id: int, quiz_id: int, body: QuizIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _one(conn, user, course_id, quiz_id)
    if _attempt_count(conn, quiz_id) and not _same_questions(_questions(conn, quiz_id), body.questions):
        raise HTTPException(409, "students have already taken this quiz, so its questions can no longer change")
    conn.execute(
        text("UPDATE quizzes SET title = :t, max_attempts = :m, show_answers = :s, published = :p WHERE id = :q"),
        {"t": body.title, "m": body.max_attempts, "s": body.show_answers, "p": body.published, "q": quiz_id},
    )
    if not _attempt_count(conn, quiz_id):
        _save_questions(conn, quiz_id, body.questions)
    return _read(conn, user, course_id, quiz_id)


@router.delete("/{quiz_id}", status_code=204)
def delete_quiz(course_id: int, quiz_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    summary = _one(conn, user, course_id, quiz_id)
    if summary.in_assignments:
        raise HTTPException(409, "this quiz is part of an assignment; take it out of the assignment first")
    if _attempt_count(conn, quiz_id):
        raise HTTPException(409, "students have taken this quiz; unpublish it instead of deleting it")
    conn.execute(text("DELETE FROM quizzes WHERE id = :q"), {"q": quiz_id})
    return Response(status_code=204)


@router.post("/{quiz_id}/attempts", response_model=AttemptOut, status_code=201)
def submit_attempt(course_id: int, quiz_id: int, body: AttemptIn, user: Student, conn: Conn):
    _check(conn, user, course_id)
    summary = _one(conn, user, course_id, quiz_id)
    questions = _questions(conn, quiz_id)
    known = {q.id for q in questions}
    asked = [a.question_id for a in body.answers]
    if len(set(asked)) != len(asked) or not set(asked) <= known:
        raise HTTPException(422, "answers must name each question of this quiz at most once")
    conn.execute(text("SELECT id FROM quizzes WHERE id = :q FOR UPDATE"), {"q": quiz_id})  # two submits at once
    used = conn.execute(
        text("SELECT count(*) FROM quiz_attempts WHERE quiz_id = :q AND user_id = :u"), {"q": quiz_id, "u": user.id}
    ).scalar_one()
    if used >= summary.max_attempts:
        raise HTTPException(409, "you have used every attempt for this quiz")
    earned, possible, review = grade(questions, body.answers)
    attempt_id = conn.execute(
        text(
            "INSERT INTO quiz_attempts (quiz_id, user_id, answers, earned, possible, fraction)"
            " VALUES (:q, :u, CAST(:a AS jsonb), :e, :p, :f) RETURNING id"
        ),
        {"q": quiz_id, "u": user.id, "a": json.dumps([a.model_dump() for a in body.answers]), "e": earned,
         "p": possible, "f": earned / possible},
    ).scalar_one()
    return AttemptOut(
        attempt_id=attempt_id, attempt_number=used + 1, attempts_left=summary.max_attempts - used - 1,
        earned=earned, possible=possible, fraction=earned / possible,
        review=review if _review_open(conn, quiz_id) else None,
    )


@router.get("/{quiz_id}/attempts/mine", response_model=MyAttempts)
def my_attempts(course_id: int, quiz_id: int, user: Student, conn: Conn):
    """The student's own attempts; the right answers only when review is open (see the module note)."""
    _check(conn, user, course_id)
    summary = _one(conn, user, course_id, quiz_id)
    rows = conn.execute(
        text("SELECT id, fraction, submitted_at, answers FROM quiz_attempts WHERE quiz_id = :q AND user_id = :u"
             " ORDER BY id"),
        {"q": quiz_id, "u": user.id},
    ).all()
    review = None
    if rows and _review_open(conn, quiz_id):
        answers = [AnswerIn(**a) for a in rows[-1].answers]
        review = grade(_questions(conn, quiz_id), answers)[2]
    return MyAttempts(
        attempts=[AttemptRow(id=r.id, number=n, fraction=r.fraction, submitted_at=r.submitted_at)
                  for n, r in enumerate(rows, start=1)],
        attempts_left=summary.max_attempts - len(rows), review=review,
    )
