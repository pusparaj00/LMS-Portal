"""What an instructor can learn from a course's data (F-90, F-91, F-92). Everything here is read-only and every
figure comes with the facts behind it, so an alert can be explained and checked, not just believed.

The thresholds are plain constants, listed in each report, so the people reading it know what a flag means.
"""
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import Connection, text

from app import grading_book
from app.routers.quizzes import _is_right, _questions
from app.schemas import (
    AnswerIn,
    AtRiskFactor,
    AtRiskReport,
    AtRiskStudent,
    Comparison,
    ContentItemReport,
    ContentReport,
    QuestionReport,
    QuizReport,
)

MISSING_MIN = 2  # assignments past due with nothing handed in
LOW_SCORE_BELOW = 50.0  # percent of the points of past-due assignments
LOW_SCORE_MIN_ASSIGNMENTS = 2
FALLING_BY = 20.0  # percentage points between earlier work and the latest two
FALLING_MIN_ASSIGNMENTS = 4
FALLING_RECENT = 2
MASTERY_BELOW = 0.40
MASTERY_MIN_CONCEPTS = 3  # concepts with evidence, so one guess is not a trend
INACTIVE_DAYS = 14
NEW_ENROLMENT_DAYS = 7  # a student who just joined has not been inactive yet
MIN_GROUP = 3  # a content comparison needs this many students on each side
CLASS_MISSED_BELOW = 50.0  # percent right
CLASS_MISSED_MIN_ANSWERS = 3

THRESHOLDS = {
    "missing_assignments": MISSING_MIN, "low_score_percent": LOW_SCORE_BELOW,
    "low_score_min_assignments": LOW_SCORE_MIN_ASSIGNMENTS, "falling_percentage_points": FALLING_BY,
    "falling_min_assignments": FALLING_MIN_ASSIGNMENTS, "low_mastery": MASTERY_BELOW,
    "low_mastery_min_concepts": MASTERY_MIN_CONCEPTS, "inactive_days": INACTIVE_DAYS,
}


def _students(conn: Connection, course_id: int) -> list:
    return conn.execute(
        text(
            "SELECT u.id, u.email, u.display_name, e.enrolled_at FROM enrollments e JOIN users u ON u.id = e.user_id"
            " WHERE e.course_id = :c AND u.role = 'student' ORDER BY COALESCE(u.display_name, u.email)"
        ),
        {"c": course_id},
    ).all()


def _last_activity(conn: Connection, course_id: int) -> dict[int, datetime]:
    rows = conn.execute(
        text(
            "SELECT user_id, max(at) AS last FROM ("
            " SELECT s.user_id, s.created_at AS at FROM submissions s JOIN problems p ON p.id = s.problem_id"
            "  WHERE p.course_id = :c"
            " UNION ALL SELECT qa.user_id, qa.submitted_at FROM quiz_attempts qa JOIN quizzes q ON q.id = qa.quiz_id"
            "  WHERE q.course_id = :c"
            " UNION ALL SELECT ws.user_id, COALESCE(ws.turned_in_at, ws.created_at) FROM work_submissions ws"
            "  JOIN assignments a ON a.id = ws.assignment_id WHERE a.course_id = :c"
            " UNION ALL SELECT ic.user_id, ic.completed_at FROM item_completions ic"
            "  JOIN content_items i ON i.id = ic.item_id JOIN modules m ON m.id = i.module_id WHERE m.course_id = :c"
            ") t GROUP BY user_id"
        ),
        {"c": course_id},
    ).all()
    return {r.user_id: r.last for r in rows}


def _mastery(conn: Connection, course_id: int) -> dict[int, list]:
    out: dict[int, list] = defaultdict(list)
    for r in conn.execute(
        text(
            "SELECT m.user_id, c.name, m.p_known FROM mastery m JOIN concepts c ON c.id = m.concept_id"
            " WHERE c.course_id = :c ORDER BY m.p_known, c.name"
        ),
        {"c": course_id},
    ):
        out[r.user_id].append((r.name.replace("_", " "), r.p_known))
    return out


def _percent(score: float, possible: float) -> float:
    return round(score / possible * 100, 1)


def at_risk(conn: Connection, course_id: int) -> AtRiskReport:
    now = datetime.now(UTC)
    due = {
        r.id: r for r in conn.execute(
            text("SELECT id, title, due_at, due_at < now() AS past_due FROM assignments WHERE course_id = :c"),
            {"c": course_id},
        )
    }
    cells: dict[int, list] = defaultdict(list)
    for s in grading_book.scores(conn, course_id):
        cells[s.student_id].append(s)
    activity, mastery = _last_activity(conn, course_id), _mastery(conn, course_id)
    flagged = []
    students = _students(conn, course_id)
    for student in students:
        factors: list[AtRiskFactor] = []
        mine = cells.get(student.id, [])
        missing = [due[c.assignment_id].title for c in mine if c.status == "missing"]
        if len(missing) >= MISSING_MIN:
            factors.append(AtRiskFactor(
                kind="missing_work", summary=f"{len(missing)} assignments are past due with nothing handed in",
                evidence=missing[:10],
            ))
        past = sorted((c for c in mine if due[c.assignment_id].past_due and c.possible > 0),
                      key=lambda c: due[c.assignment_id].due_at)
        if len(past) >= LOW_SCORE_MIN_ASSIGNMENTS:
            overall = _percent(sum(c.score for c in past), sum(c.possible for c in past))
            if overall < LOW_SCORE_BELOW:
                factors.append(AtRiskFactor(
                    kind="low_scores", summary=f"{overall}% of the points on {len(past)} past-due assignments",
                    evidence=[f"{due[c.assignment_id].title}: {c.score:g} of {c.possible:g}" for c in past[-10:]],
                ))
        if len(past) >= FALLING_MIN_ASSIGNMENTS:
            percents = [c.score / c.possible * 100 for c in past]
            earlier, recent = percents[:-FALLING_RECENT], percents[-FALLING_RECENT:]
            drop = sum(earlier) / len(earlier) - sum(recent) / len(recent)
            if drop >= FALLING_BY:
                factors.append(AtRiskFactor(
                    kind="falling_scores", summary=f"the latest {FALLING_RECENT} scores are {round(drop)} points lower",
                    evidence=[f"earlier assignments averaged {sum(earlier) / len(earlier):.0f}%",
                              f"the latest {FALLING_RECENT} averaged {sum(recent) / len(recent):.0f}%"],
                ))
        known = mastery.get(student.id, [])
        if len(known) >= MASTERY_MIN_CONCEPTS:
            average = sum(p for _, p in known) / len(known)
            if average < MASTERY_BELOW:
                factors.append(AtRiskFactor(
                    kind="low_mastery",
                    summary=f"average mastery is {average * 100:.0f}% over {len(known)} concepts with evidence",
                    evidence=[f"{name}: {p * 100:.0f}%" for name, p in known[:3]],
                ))
        last = activity.get(student.id)
        joined_days = (now - student.enrolled_at).days
        if joined_days >= NEW_ENROLMENT_DAYS and (last is None or (now - last).days >= INACTIVE_DAYS):
            factors.append(AtRiskFactor(
                kind="inactive",
                summary=(f"no activity for {(now - last).days} days" if last
                         else f"no activity since joining {joined_days} days ago"),
                evidence=[f"last activity: {last:%Y-%m-%d}" if last
                          else "nothing handed in, answered, run or completed"],
            ))
        if factors:
            flagged.append(AtRiskStudent(
                student_id=student.id, label=grading_book.label(student.email, student.display_name),
                synthetic=student.email.endswith(("@synthetic.local", "@eval.local")), factors=factors,
            ))
    flagged.sort(key=lambda s: (-len(s.factors), s.label))
    return AtRiskReport(checked=len(students), thresholds=THRESHOLDS, students=flagged)


def quiz_report(conn: Connection, course_id: int, quiz_id: int) -> QuizReport:
    head = conn.execute(
        text("SELECT title FROM quizzes WHERE id = :q AND course_id = :c"), {"q": quiz_id, "c": course_id}
    ).first()
    if head is None:
        return None
    questions = _questions(conn, quiz_id)
    latest = conn.execute(
        text(
            "SELECT DISTINCT ON (user_id) user_id, answers, fraction FROM quiz_attempts WHERE quiz_id = :q"
            " ORDER BY user_id, id DESC"
        ),
        {"q": quiz_id},
    ).all()
    attempts = conn.execute(
        text("SELECT count(*) FROM quiz_attempts WHERE quiz_id = :q"), {"q": quiz_id}
    ).scalar_one()
    out = []
    for q in questions:
        answered = right = 0
        chosen: dict[int, int] = defaultdict(int)
        for row in latest:
            given = next((AnswerIn(**a) for a in row.answers if a["question_id"] == q.id), None)
            if given is None or not (given.choices or (given.text or "").strip()):
                continue
            answered += 1
            right += _is_right(q, given)
            for choice in given.choices:
                chosen[choice] += 1
        percent = _percent(right, answered) if answered else None
        out.append(QuestionReport(
            question_id=q.id, prompt=q.prompt, kind=q.kind, options=q.options, answered=answered, right=right,
            percent_right=percent,
            chosen_counts=[chosen[i] for i in range(len(q.options))] if q.kind != "short" else [],
            right_choices=q.correct if q.kind != "short" else [],
            class_missed=percent is not None and answered >= CLASS_MISSED_MIN_ANSWERS and percent < CLASS_MISSED_BELOW,
        ))
    return QuizReport(
        quiz_id=quiz_id, title=head.title, students=len(latest), attempts=attempts,
        average_percent=round(sum(r.fraction for r in latest) / len(latest) * 100, 1) if latest else None,
        questions=out,
    )


def _compare(with_item: list[float], without: list[float]) -> Comparison:
    enough = len(with_item) >= MIN_GROUP and len(without) >= MIN_GROUP
    mean_with = round(sum(with_item) / len(with_item), 1) if with_item else None
    mean_without = round(sum(without) / len(without), 1) if without else None
    return Comparison(
        n_with=len(with_item), n_without=len(without), average_with=mean_with, average_without=mean_without,
        difference=round(mean_with - mean_without, 1) if enough else None,
    )


def _split(ids: list[int], finished: set[int], metric: dict[int, float]) -> tuple[list[float], list[float]]:
    """The metric of the students who finished an item, and of those who did not (students without one are left out)."""
    return (
        [metric[i] for i in ids if i in finished and i in metric],
        [metric[i] for i in ids if i not in finished and i in metric],
    )


def content_report(conn: Connection, course_id: int) -> ContentReport:
    students = _students(conn, course_id)
    points: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for s in grading_book.scores(conn, course_id):
        points[s.student_id][0] += s.score
        points[s.student_id][1] += s.possible
    score_of = {sid: _percent(a, b) for sid, (a, b) in points.items() if b > 0}
    mastery = _mastery(conn, course_id)
    mastery_of = {sid: round(sum(p for _, p in rows) / len(rows) * 100, 1) for sid, rows in mastery.items()}
    done: dict[int, set[int]] = defaultdict(set)
    for r in conn.execute(
        text(
            "SELECT ic.item_id, ic.user_id FROM item_completions ic JOIN content_items i ON i.id = ic.item_id"
            " JOIN modules m ON m.id = i.module_id WHERE m.course_id = :c"
        ),
        {"c": course_id},
    ):
        done[r.item_id].add(r.user_id)
    items = conn.execute(
        text(
            "SELECT i.id, i.title, i.kind, m.title AS module FROM content_items i JOIN modules m ON m.id = i.module_id"
            " WHERE m.course_id = :c ORDER BY m.position, m.id, i.position, i.id"
        ),
        {"c": course_id},
    ).all()
    ids = [s.id for s in students]
    report = []
    for item in items:
        finished = done[item.id]
        report.append(ContentItemReport(
            item_id=item.id, title=item.title, module=item.module, kind=item.kind,
            completed=sum(1 for i in ids if i in finished), not_completed=sum(1 for i in ids if i not in finished),
            scores=_compare(*_split(ids, finished, score_of)), mastery=_compare(*_split(ids, finished, mastery_of)),
        ))
    return ContentReport(students=len(students), min_group=MIN_GROUP, items=report)
