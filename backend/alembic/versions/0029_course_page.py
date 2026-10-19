"""Course page structure and scheduling (F-84, F-85, F-86).

Announcements can be drafts or scheduled; an assignment can sit under a topic (a course module) and be given to chosen
students only. assignment_scores skips an assignment for a student it was not given to.

Revision ID: 0029
Revises: 0028
"""
from alembic import op

revision = "0029"
down_revision = "0028"

_BEFORE = """
    CREATE OR REPLACE FUNCTION assignment_scores(p_course integer, p_only integer)
    RETURNS TABLE (student_id integer, assignment_id integer, score double precision, with_late double precision,
                   possible double precision, tried_on_time boolean, tried_late boolean, past_due boolean)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        WITH items AS (
            SELECT a.id AS assignment_id, a.due_at, 'p'::text AS kind, ap.problem_id AS ref_id, ap.points
            FROM assignments a JOIN assignment_problems ap ON ap.assignment_id = a.id WHERE a.course_id = p_course
            UNION ALL
            SELECT a.id, a.due_at, 'q', aq.quiz_id, aq.points
            FROM assignments a JOIN assignment_quizzes aq ON aq.assignment_id = a.id WHERE a.course_id = p_course
            UNION ALL
            SELECT a.id, a.due_at, 'w', a.id, aw.points
            FROM assignments a JOIN assignment_work aw ON aw.assignment_id = a.id WHERE a.course_id = p_course
        ),
        students AS (
            SELECT u.id FROM enrollments e JOIN users u ON u.id = e.user_id
            WHERE e.course_id = p_course AND u.role = 'student' AND (p_only IS NULL OR u.id = p_only)
        ),
        attempts AS (
            SELECT i.assignment_id, i.kind, i.ref_id, s.user_id,
                   max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at <= i.due_at) AS on_time,
                   max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at > i.due_at) AS late,
                   bool_or(s.created_at <= i.due_at) AS tried_on_time,
                   bool_or(s.created_at > i.due_at) AS tried_late
            FROM items i JOIN submissions s ON i.kind = 'p' AND s.problem_id = i.ref_id
            JOIN run_results r ON r.submission_id = s.id
            WHERE s.user_id IN (SELECT id FROM students)
            GROUP BY i.assignment_id, i.kind, i.ref_id, s.user_id
            UNION ALL
            SELECT i.assignment_id, i.kind, i.ref_id, qa.user_id,
                   max(qa.fraction) FILTER (WHERE qa.submitted_at <= i.due_at),
                   max(qa.fraction) FILTER (WHERE qa.submitted_at > i.due_at),
                   bool_or(qa.submitted_at <= i.due_at),
                   bool_or(qa.submitted_at > i.due_at)
            FROM items i JOIN quiz_attempts qa ON i.kind = 'q' AND qa.quiz_id = i.ref_id
            WHERE qa.user_id IN (SELECT id FROM students)
            GROUP BY i.assignment_id, i.kind, i.ref_id, qa.user_id
            UNION ALL
            SELECT i.assignment_id, i.kind, i.ref_id, ws.user_id,
                   max(ws.score / i.points) FILTER (WHERE ws.returned_at IS NOT NULL AND ws.turned_in_at <= i.due_at),
                   max(ws.score / i.points) FILTER (WHERE ws.returned_at IS NOT NULL AND ws.turned_in_at > i.due_at),
                   bool_or(ws.turned_in_at <= i.due_at),
                   bool_or(ws.turned_in_at > i.due_at)
            FROM items i JOIN work_submissions ws ON i.kind = 'w' AND ws.assignment_id = i.assignment_id
            WHERE ws.user_id IN (SELECT id FROM students) AND ws.status = 'turned_in'
            GROUP BY i.assignment_id, i.kind, i.ref_id, ws.user_id
        )
        SELECT st.id, i.assignment_id,
               sum(i.points * COALESCE(a.on_time, 0)),
               sum(i.points * GREATEST(COALESCE(a.on_time, 0), COALESCE(a.late, 0))),
               sum(i.points),
               COALESCE(bool_or(a.tried_on_time), false),
               COALESCE(bool_or(a.tried_late), false),
               bool_and(now() > i.due_at)
        FROM students st CROSS JOIN items i
        LEFT JOIN attempts a ON a.assignment_id = i.assignment_id AND a.kind = i.kind AND a.ref_id = i.ref_id
                             AND a.user_id = st.id
        GROUP BY st.id, i.assignment_id
    $$;
"""

_AFTER = """
    CREATE OR REPLACE FUNCTION assignment_scores(p_course integer, p_only integer)
    RETURNS TABLE (student_id integer, assignment_id integer, score double precision, with_late double precision,
                   possible double precision, tried_on_time boolean, tried_late boolean, past_due boolean)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        WITH items AS (
            SELECT a.id AS assignment_id, a.due_at, 'p'::text AS kind, ap.problem_id AS ref_id, ap.points
            FROM assignments a JOIN assignment_problems ap ON ap.assignment_id = a.id WHERE a.course_id = p_course
            UNION ALL
            SELECT a.id, a.due_at, 'q', aq.quiz_id, aq.points
            FROM assignments a JOIN assignment_quizzes aq ON aq.assignment_id = a.id WHERE a.course_id = p_course
            UNION ALL
            SELECT a.id, a.due_at, 'w', a.id, aw.points
            FROM assignments a JOIN assignment_work aw ON aw.assignment_id = a.id WHERE a.course_id = p_course
        ),
        students AS (
            SELECT u.id FROM enrollments e JOIN users u ON u.id = e.user_id
            WHERE e.course_id = p_course AND u.role = 'student' AND (p_only IS NULL OR u.id = p_only)
        ),
        attempts AS (
            SELECT i.assignment_id, i.kind, i.ref_id, s.user_id,
                   max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at <= i.due_at) AS on_time,
                   max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at > i.due_at) AS late,
                   bool_or(s.created_at <= i.due_at) AS tried_on_time,
                   bool_or(s.created_at > i.due_at) AS tried_late
            FROM items i JOIN submissions s ON i.kind = 'p' AND s.problem_id = i.ref_id
            JOIN run_results r ON r.submission_id = s.id
            WHERE s.user_id IN (SELECT id FROM students)
            GROUP BY i.assignment_id, i.kind, i.ref_id, s.user_id
            UNION ALL
            SELECT i.assignment_id, i.kind, i.ref_id, qa.user_id,
                   max(qa.fraction) FILTER (WHERE qa.submitted_at <= i.due_at),
                   max(qa.fraction) FILTER (WHERE qa.submitted_at > i.due_at),
                   bool_or(qa.submitted_at <= i.due_at),
                   bool_or(qa.submitted_at > i.due_at)
            FROM items i JOIN quiz_attempts qa ON i.kind = 'q' AND qa.quiz_id = i.ref_id
            WHERE qa.user_id IN (SELECT id FROM students)
            GROUP BY i.assignment_id, i.kind, i.ref_id, qa.user_id
            UNION ALL
            SELECT i.assignment_id, i.kind, i.ref_id, ws.user_id,
                   max(ws.score / i.points) FILTER (WHERE ws.returned_at IS NOT NULL AND ws.turned_in_at <= i.due_at),
                   max(ws.score / i.points) FILTER (WHERE ws.returned_at IS NOT NULL AND ws.turned_in_at > i.due_at),
                   bool_or(ws.turned_in_at <= i.due_at),
                   bool_or(ws.turned_in_at > i.due_at)
            FROM items i JOIN work_submissions ws ON i.kind = 'w' AND ws.assignment_id = i.assignment_id
            WHERE ws.user_id IN (SELECT id FROM students) AND ws.status = 'turned_in'
            GROUP BY i.assignment_id, i.kind, i.ref_id, ws.user_id
        )
        SELECT st.id, i.assignment_id,
               sum(i.points * COALESCE(a.on_time, 0)),
               sum(i.points * GREATEST(COALESCE(a.on_time, 0), COALESCE(a.late, 0))),
               sum(i.points),
               COALESCE(bool_or(a.tried_on_time), false),
               COALESCE(bool_or(a.tried_late), false),
               bool_and(now() > i.due_at)
        FROM students st CROSS JOIN items i
        LEFT JOIN attempts a ON a.assignment_id = i.assignment_id AND a.kind = i.kind AND a.ref_id = i.ref_id
                             AND a.user_id = st.id
        WHERE NOT EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = i.assignment_id)
           OR EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = i.assignment_id AND g.user_id = st.id)
        GROUP BY st.id, i.assignment_id
    $$;
"""


def upgrade() -> None:
    op.execute("""
    ALTER TABLE announcements
        ADD COLUMN is_draft boolean NOT NULL DEFAULT false,
        ADD COLUMN publish_at timestamptz,
        ADD COLUMN notified_at timestamptz,
        ADD CONSTRAINT announcements_draft_or_scheduled CHECK (NOT (is_draft AND publish_at IS NOT NULL));
    UPDATE announcements SET notified_at = now();
    ALTER TABLE assignments ADD COLUMN module_id integer REFERENCES modules(id) ON DELETE SET NULL;
    CREATE TABLE assignment_students (
        assignment_id integer NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
        user_id integer NOT NULL REFERENCES users(id),
        PRIMARY KEY (assignment_id, user_id)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON assignment_students TO lms_api;
    """)
    op.execute(_AFTER)


def downgrade() -> None:
    op.execute(_BEFORE)
    op.execute("""
    DROP TABLE assignment_students;
    ALTER TABLE assignments DROP COLUMN module_id;
    ALTER TABLE announcements DROP CONSTRAINT announcements_draft_or_scheduled,
        DROP COLUMN notified_at, DROP COLUMN publish_at, DROP COLUMN is_draft;
    """)
