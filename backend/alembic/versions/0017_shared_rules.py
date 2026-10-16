"""The assignment-score rule and the next-problem rule as database functions (F-04, F-52, F-60, TR-A-02).

The gradebook, the student dashboard and the assistant's recommend and lms routes all answer from these, so they
cannot disagree. The assistant reads through the read-only lms_chat role, which may not read submissions, run results
or users (it would see every student's code and the password hashes). These functions run as their owner and return
only numbers, titles and dates, so that role can call them without being granted those tables. It may also read the
course-level tables the routes need, which hold no personal data.

Revision ID: 0017
"""
from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION assignment_scores(p_course integer, p_only integer)
    RETURNS TABLE (student_id integer, assignment_id integer, score double precision, with_late double precision,
                   possible double precision, tried_on_time boolean, tried_late boolean, past_due boolean)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        WITH items AS (
            SELECT a.id AS assignment_id, a.due_at, ap.problem_id, ap.points
            FROM assignments a JOIN assignment_problems ap ON ap.assignment_id = a.id WHERE a.course_id = p_course
        ),
        students AS (
            SELECT u.id FROM enrollments e JOIN users u ON u.id = e.user_id
            WHERE e.course_id = p_course AND u.role = 'student' AND (p_only IS NULL OR u.id = p_only)
        ),
        attempts AS (
            SELECT i.assignment_id, i.problem_id, s.user_id,
                   max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at <= i.due_at) AS on_time,
                   max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at > i.due_at) AS late,
                   bool_or(s.created_at <= i.due_at) AS tried_on_time,
                   bool_or(s.created_at > i.due_at) AS tried_late
            FROM items i JOIN submissions s ON s.problem_id = i.problem_id JOIN run_results r ON r.submission_id = s.id
            WHERE s.user_id IN (SELECT id FROM students)
            GROUP BY i.assignment_id, i.problem_id, s.user_id
        )
        SELECT st.id, i.assignment_id,
               sum(i.points * COALESCE(a.on_time, 0)),
               sum(i.points * GREATEST(COALESCE(a.on_time, 0), COALESCE(a.late, 0))),
               sum(i.points),
               COALESCE(bool_or(a.tried_on_time), false),
               COALESCE(bool_or(a.tried_late), false),
               bool_and(now() > i.due_at)
        FROM students st CROSS JOIN items i
        LEFT JOIN attempts a ON a.assignment_id = i.assignment_id AND a.problem_id = i.problem_id AND a.user_id = st.id
        GROUP BY st.id, i.assignment_id
    $$;

    CREATE FUNCTION next_problem(p_user integer, p_course integer, p_concept integer)
    RETURNS TABLE (problem_id integer, title text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        SELECT p.id, p.title FROM problems p
        JOIN problem_concepts pc ON pc.problem_id = p.id AND pc.concept_id = p_concept
        WHERE p.kind = 'code' AND p.course_id = p_course AND p.archived_at IS NULL AND NOT EXISTS (
            SELECT 1 FROM submissions s JOIN run_results r ON r.submission_id = s.id
            WHERE s.problem_id = p.id AND s.user_id = p_user AND r.status = 'passed')
        ORDER BY p.difficulty_b, p.id LIMIT 1
    $$;

    REVOKE ALL ON FUNCTION assignment_scores(integer, integer), next_problem(integer, integer, integer) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION assignment_scores(integer, integer), next_problem(integer, integer, integer)
        TO lms_api, lms_chat;
    GRANT SELECT ON assignments, announcements, documents, chunks TO lms_chat;
    """)


def downgrade() -> None:
    op.execute("""
    REVOKE SELECT ON assignments, announcements, documents, chunks FROM lms_chat;
    DROP FUNCTION next_problem(integer, integer, integer);
    DROP FUNCTION assignment_scores(integer, integer);
    """)
