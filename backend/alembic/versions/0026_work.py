"""Handed-in work and manual grading (F-73, F-74, F-75, F-76, F-77).

An assignment may ask for work (instructions, points, and which of file, link or text it accepts). A student has one
row per assignment: a draft, then turned in. The instructor scores it and returns it; only a returned score counts in
assignment_scores, by the same late rule as problems and quizzes (turned in after the due time shows only as with_late).

Revision ID: 0026
Revises: 0025
"""
from alembic import op

revision = "0026"
down_revision = "0025"

_WITH_QUIZZES = """
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

_WITH_WORK = """
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


def upgrade() -> None:
    op.execute("""
    CREATE TABLE assignment_work (
        assignment_id integer PRIMARY KEY REFERENCES assignments(id) ON DELETE CASCADE,
        instructions text NOT NULL CHECK (length(instructions) BETWEEN 1 AND 5000),
        points double precision NOT NULL CHECK (points > 0 AND points <= 100),
        allow_file boolean NOT NULL DEFAULT true,
        allow_link boolean NOT NULL DEFAULT true,
        allow_text boolean NOT NULL DEFAULT true,
        CHECK (allow_file OR allow_link OR allow_text)
    );
    CREATE TABLE work_submissions (
        id serial PRIMARY KEY,
        assignment_id integer NOT NULL REFERENCES assignments(id),
        user_id integer NOT NULL REFERENCES users(id),
        status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'turned_in')),
        body text CHECK (body IS NULL OR length(body) BETWEEN 1 AND 20000),
        link text CHECK (link IS NULL OR (length(link) <= 2000 AND link ~ '^https?://[^[:space:]]+$')),
        file_name text CHECK (file_name IS NULL OR length(file_name) BETWEEN 1 AND 200),
        file_data bytea CHECK (file_data IS NULL OR octet_length(file_data) <= 5000000),
        created_at timestamptz NOT NULL DEFAULT now(),
        turned_in_at timestamptz,
        score double precision CHECK (score IS NULL OR score >= 0),
        feedback text CHECK (feedback IS NULL OR length(feedback) <= 5000),
        graded_at timestamptz,
        graded_by integer REFERENCES users(id),
        returned_at timestamptz,
        UNIQUE (assignment_id, user_id),
        CHECK ((file_name IS NULL) = (file_data IS NULL)),
        CHECK ((status = 'turned_in') = (turned_in_at IS NOT NULL)),
        CHECK (returned_at IS NULL OR graded_at IS NOT NULL),
        CHECK ((graded_at IS NULL) = (score IS NULL))
    );
    CREATE INDEX work_submissions_user ON work_submissions (user_id);
    CREATE TABLE work_comments (
        id serial PRIMARY KEY,
        submission_id integer NOT NULL REFERENCES work_submissions(id) ON DELETE CASCADE,
        author_id integer NOT NULL REFERENCES users(id),
        body text NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX work_comments_submission ON work_comments (submission_id, id);
    GRANT SELECT, INSERT, UPDATE, DELETE ON assignment_work, work_submissions, work_comments TO lms_api;
    GRANT USAGE ON SEQUENCE work_submissions_id_seq, work_comments_id_seq TO lms_api;
    """)
    op.execute(_WITH_WORK)


def downgrade() -> None:
    op.execute(_WITH_QUIZZES)
    op.execute("DROP TABLE work_comments; DROP TABLE work_submissions; DROP TABLE assignment_work;")
