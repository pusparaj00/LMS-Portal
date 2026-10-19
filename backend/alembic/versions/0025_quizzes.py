"""Quizzes (F-71, F-72, F-75): quizzes, their questions, graded attempts, and quizzes inside assignments.

assignment_scores keeps its signature and its late rule; a quiz inside an assignment scores its points times the fraction
of the best attempt, on time or late, exactly as a coding problem scores its share of passed tests.

Revision ID: 0025
Revises: 0024
"""
from alembic import op

revision = "0025"
down_revision = "0024"

_PROBLEMS_ONLY = """
    CREATE OR REPLACE FUNCTION assignment_scores(p_course integer, p_only integer)
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
"""

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


def upgrade() -> None:
    op.execute("""
    CREATE TABLE quizzes (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
        show_answers boolean NOT NULL DEFAULT false,
        published boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX quizzes_course ON quizzes (course_id, id);
    CREATE TABLE quiz_questions (
        id serial PRIMARY KEY,
        quiz_id integer NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
        position integer NOT NULL,
        kind text NOT NULL CHECK (kind IN ('single', 'multiple', 'short')),
        prompt text NOT NULL CHECK (length(prompt) BETWEEN 1 AND 2000),
        options jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(options) = 'array'),
        correct jsonb NOT NULL CHECK (jsonb_typeof(correct) = 'array' AND jsonb_array_length(correct) >= 1),
        weight double precision NOT NULL DEFAULT 1 CHECK (weight > 0 AND weight <= 100)
    );
    CREATE INDEX quiz_questions_quiz ON quiz_questions (quiz_id, position, id);
    CREATE TABLE quiz_attempts (
        id serial PRIMARY KEY,
        quiz_id integer NOT NULL REFERENCES quizzes(id),
        user_id integer NOT NULL REFERENCES users(id),
        answers jsonb NOT NULL,
        earned double precision NOT NULL CHECK (earned >= 0),
        possible double precision NOT NULL CHECK (possible > 0),
        fraction double precision NOT NULL CHECK (fraction >= 0 AND fraction <= 1),
        submitted_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX quiz_attempts_user ON quiz_attempts (quiz_id, user_id, id);
    CREATE TABLE assignment_quizzes (
        assignment_id integer NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
        quiz_id integer NOT NULL REFERENCES quizzes(id),
        points double precision NOT NULL DEFAULT 1 CHECK (points > 0 AND points <= 100),
        PRIMARY KEY (assignment_id, quiz_id)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON quizzes, quiz_questions, quiz_attempts, assignment_quizzes TO lms_api;
    GRANT USAGE ON SEQUENCE quizzes_id_seq, quiz_questions_id_seq, quiz_attempts_id_seq TO lms_api;
    """)
    op.execute(_WITH_QUIZZES)


def downgrade() -> None:
    op.execute(_PROBLEMS_ONLY)
    op.execute("DROP TABLE assignment_quizzes; DROP TABLE quiz_attempts; DROP TABLE quiz_questions; DROP TABLE quizzes;")
