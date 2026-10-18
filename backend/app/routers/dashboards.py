"""Dashboard data for both roles (F-63, F-64) and course ratings (F-65). Every figure is a query over the caller's own
rows: a student sees only their own scores, an instructor only the courses they teach."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text

from app import grading_book
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import (
    AssignmentProgress,
    CourseAnalytics,
    CourseGrades,
    CourseProgress,
    CourseRatings,
    GradeLine,
    InstructorCourseStats,
    InstructorStats,
    RatingIn,
    RatingOut,
    RatingSummary,
    ScoreBucket,
    StudentStats,
    UpcomingAssignment,
)

router = APIRouter(tags=["dashboards"])
Student = Annotated[CurrentUser, Depends(require_role("student"))]
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Staff = Annotated[CurrentUser, Depends(require_role("instructor", "admin"))]
Member = Annotated[CurrentUser, Depends(current_user)]
UPCOMING_LIMIT = 5
REVIEW_LIMIT = 50
BUCKETS = ["0-19%", "20-39%", "40-59%", "60-79%", "80-100%"]
STUDENTS = (
    "SELECT count(*) FROM enrollments e JOIN users u ON u.id = e.user_id"
    " WHERE e.course_id = :c AND u.role = 'student'"
)


def _percent(score: float, possible: float) -> float | None:
    return round(score / possible * 100, 1) if possible else None


def _assignment_rows(conn: Connection, course_id: int):
    return conn.execute(
        text("SELECT id, title, due_at FROM assignments WHERE course_id = :c ORDER BY due_at, id"), {"c": course_id}
    ).all()


def _student_courses(conn: Connection, user_id: int) -> list[CourseGrades]:
    courses = conn.execute(
        text(
            "SELECT c.id, c.title FROM enrollments e JOIN courses c ON c.id = e.course_id"
            " WHERE e.user_id = :u AND c.archived_at IS NULL ORDER BY c.title, c.id"
        ),
        {"u": user_id},
    ).all()
    out = []
    for course in courses:
        mine = {s.assignment_id: s for s in grading_book.scores(conn, course.id, only_student=user_id)}
        lines = [
            GradeLine(
                assignment_id=a.id, title=a.title, due_at=a.due_at, score=mine[a.id].score,
                with_late=mine[a.id].with_late, possible=mine[a.id].possible, status=mine[a.id].status,
            )
            for a in _assignment_rows(conn, course.id)
            if a.id in mine  # an assignment with no problems has no score row
        ]
        score = round(sum(line.score for line in lines), 4)
        possible = sum(line.possible for line in lines)
        out.append(CourseGrades(
            course_id=course.id, title=course.title, score=score, possible=possible,
            percent=_percent(score, possible), assignments=lines,
        ))
    return out


@router.get("/students/me/grades", response_model=list[CourseGrades])
def my_grades(user: Student, conn: Conn):
    """F-63: the student's own score for every assignment of every course they are enrolled in."""
    return _student_courses(conn, user.id)


@router.get("/students/me/stats", response_model=StudentStats)
def my_stats(user: Student, conn: Conn):
    """F-63: enrolled courses, average score, progress per course and the next assignments still to finish."""
    courses = _student_courses(conn, user.id)
    now = conn.execute(text("SELECT now()")).scalar_one()
    progress = []
    upcoming = []
    for c in courses:
        future = [a for a in c.assignments if a.due_at > now]
        progress.append(CourseProgress(
            course_id=c.course_id, title=c.title, assignments=len(c.assignments),
            completed=sum(a.status == "complete" for a in c.assignments), score=c.score, possible=c.possible,
            percent=c.percent, next_due_at=min((a.due_at for a in future), default=None),
        ))
        upcoming += [
            UpcomingAssignment(
                assignment_id=a.assignment_id, course_id=c.course_id, course_title=c.title, title=a.title,
                due_at=a.due_at, status=a.status,
            )
            for a in future
            if a.status != "complete"
        ]
    upcoming.sort(key=lambda a: a.due_at)
    score = sum(c.score for c in courses)
    possible = sum(c.possible for c in courses)
    return StudentStats(
        enrolled_courses=len(courses), average_percent=_percent(score, possible),
        assignments_complete=sum(p.completed for p in progress), assignments_total=sum(p.assignments for p in progress),
        courses=progress, upcoming=upcoming[:UPCOMING_LIMIT],
    )


def _rating_summary(conn: Connection, course_id: int) -> RatingSummary:
    row = conn.execute(
        text(
            "SELECT count(*) AS n, round(avg(course_rating), 2)::float AS c,"
            " round(avg(instructor_rating), 2)::float AS i FROM ratings WHERE course_id = :c"
        ),
        {"c": course_id},
    ).one()
    return RatingSummary(count=row.n, average_course=row.c, average_instructor=row.i)


def _completion(conn: Connection, course_id: int) -> tuple[float | None, list]:
    cells = grading_book.scores(conn, course_id)
    done = sum(s.status == "complete" for s in cells)
    return (round(done / len(cells) * 100, 1) if cells else None), cells


def _submissions(conn: Connection, course_id: int) -> tuple[int, int]:
    """Submissions to the course's problems by students still enrolled: all of them, and those of the last 7 days."""
    row = conn.execute(
        text(
            "SELECT count(*) AS total, count(*) FILTER (WHERE s.created_at > now() - interval '7 days') AS recent"
            " FROM submissions s JOIN problems p ON p.id = s.problem_id"
            " JOIN enrollments e ON e.user_id = s.user_id AND e.course_id = p.course_id"
            " WHERE p.course_id = :c"
        ),
        {"c": course_id},
    ).one()
    return row.total, row.recent


@router.get("/instructor/stats", response_model=InstructorStats)
def instructor_stats(user: Instructor, conn: Conn):
    """F-64: totals over the instructor's own live courses and their next assignments."""
    courses = conn.execute(
        text("SELECT id, title FROM courses WHERE instructor_id = :u AND archived_at IS NULL ORDER BY title, id"),
        {"u": user.id},
    ).all()
    stats = []
    for course in courses:
        completion, _ = _completion(conn, course.id)
        ratings = _rating_summary(conn, course.id)
        stats.append(InstructorCourseStats(
            course_id=course.id, title=course.title,
            students=conn.execute(text(STUDENTS), {"c": course.id}).scalar_one(),
            assignments=len(_assignment_rows(conn, course.id)),
            submissions_7d=_submissions(conn, course.id)[1], completion_rate=completion,
            rating_count=ratings.count, average_course_rating=ratings.average_course,
        ))
    upcoming = [
        UpcomingAssignment(
            assignment_id=r.id, course_id=r.course_id, course_title=r.course_title, title=r.title, due_at=r.due_at,
            students_complete=r.done, students=r.students,
        )
        for r in conn.execute(
            text(
                "SELECT a.id, a.course_id, c.title AS course_title, a.title, a.due_at,"
                " (SELECT count(*) FROM enrollments e JOIN users u ON u.id = e.user_id"
                "  WHERE e.course_id = a.course_id AND u.role = 'student') AS students,"
                " (SELECT count(*) FROM assignment_scores(a.course_id, NULL) s"
                "  WHERE s.assignment_id = a.id AND s.score >= s.possible) AS done"
                " FROM assignments a JOIN courses c ON c.id = a.course_id"
                " WHERE c.instructor_id = :u AND c.archived_at IS NULL AND a.due_at > now()"
                " ORDER BY a.due_at, a.id"
            ),
            {"u": user.id},
        )
    ]
    distinct_students = conn.execute(
        text(
            "SELECT count(DISTINCT e.user_id) FROM enrollments e JOIN courses c ON c.id = e.course_id"
            " JOIN users u ON u.id = e.user_id"
            " WHERE c.instructor_id = :u AND c.archived_at IS NULL AND u.role = 'student'"
        ),
        {"u": user.id},
    ).scalar_one()
    return InstructorStats(
        courses=len(courses), students=distinct_students, upcoming_assignments=len(upcoming),
        submissions_7d=sum(s.submissions_7d for s in stats), course_stats=stats, upcoming=upcoming[:UPCOMING_LIMIT],
    )


@router.get("/courses/{course_id}/analytics", response_model=CourseAnalytics)
def course_analytics(course_id: int, user: Staff, conn: Conn):
    """F-64: completion, score distribution and where each assignment stands, for one course."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    title = conn.execute(text("SELECT title FROM courses WHERE id = :c"), {"c": course_id}).scalar_one_or_none()
    if title is None:
        raise HTTPException(404, "course not found")
    completion, cells = _completion(conn, course_id)
    totals: dict[int, list[float]] = {}
    for s in cells:
        t = totals.setdefault(s.student_id, [0.0, 0.0])
        t[0] += s.score
        t[1] += s.possible
    percents = [p for p in (_percent(*t) for t in totals.values()) if p is not None]
    counts = [0] * len(BUCKETS)
    for p in percents:
        counts[min(int(p // 20), len(BUCKETS) - 1)] += 1
    per = []
    for a in _assignment_rows(conn, course_id):
        statuses = [s.status for s in cells if s.assignment_id == a.id]
        per.append(AssignmentProgress(
            assignment_id=a.id, title=a.title, due_at=a.due_at, complete=statuses.count("complete"),
            in_progress=statuses.count("in_progress"), late=statuses.count("late"),
            missing=statuses.count("missing"), not_started=statuses.count("not_started"),
        ))
    total, recent = _submissions(conn, course_id)
    return CourseAnalytics(
        course_id=course_id, title=title, students=conn.execute(text(STUDENTS), {"c": course_id}).scalar_one(),
        assignments=len(per), submissions_total=total, submissions_7d=recent, completion_rate=completion,
        average_percent=round(sum(percents) / len(percents), 1) if percents else None,
        distribution=[ScoreBucket(label=b, students=n) for b, n in zip(BUCKETS, counts, strict=True)],
        per_assignment=per, ratings=_rating_summary(conn, course_id),
    )


def _ratings(conn: Connection, user: CurrentUser, course_id: int) -> CourseRatings:
    mine = None
    if user.role == "student":
        row = conn.execute(
            text("SELECT course_rating, instructor_rating, review, created_at FROM ratings"
                 " WHERE course_id = :c AND user_id = :u"),
            {"c": course_id, "u": user.id},
        ).mappings().first()
        mine = RatingOut(**row) if row else None
    reviews = conn.execute(
        text(
            "SELECT course_rating, instructor_rating, review, created_at FROM ratings"
            " WHERE course_id = :c AND review IS NOT NULL ORDER BY created_at DESC, id DESC LIMIT :n"
        ),
        {"c": course_id, "n": REVIEW_LIMIT},
    ).mappings()
    return CourseRatings(
        summary=_rating_summary(conn, course_id), mine=mine,
        reviews=[RatingOut(**r) for r in reviews],  # no author: reviews are anonymous to everyone
    )


@router.get("/courses/{course_id}/ratings", response_model=CourseRatings)
def read_ratings(course_id: int, user: Member, conn: Conn):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")
    return _ratings(conn, user, course_id)


@router.put("/courses/{course_id}/ratings", response_model=CourseRatings)
def rate_course(course_id: int, body: RatingIn, user: Student, conn: Conn):
    """One rating per enrolled student; saving again replaces it."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "only a student enrolled in the course can rate it")
    review = body.review.strip() if body.review else None
    conn.execute(
        text(
            "INSERT INTO ratings (course_id, user_id, course_rating, instructor_rating, review)"
            " VALUES (:c, :u, :cr, :ir, :r)"
            " ON CONFLICT (course_id, user_id) DO UPDATE SET course_rating = :cr, instructor_rating = :ir,"
            " review = :r, updated_at = now()"
        ),
        {"c": course_id, "u": user.id, "cr": body.course_rating, "ir": body.instructor_rating, "r": review or None},
    )
    return _ratings(conn, user, course_id)
