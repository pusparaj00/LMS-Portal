"""Grading structure (F-87, F-88, F-89): grade categories with weights, rubrics, and audited score overrides.

assignment_scores now lets an override replace a student's computed score for one assignment; the override carries a
reason and who set it. A rubric belongs to a course and is attached to an assignment's handed-in work; the levels a
teacher picks for each criterion are stored with the work.

Revision ID: 0030
Revises: 0029
"""
from alembic import op

revision = "0030"
down_revision = "0029"

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
        WHERE NOT EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = i.assignment_id)
           OR EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = i.assignment_id AND g.user_id = st.id)
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
               COALESCE(max(o.score), sum(i.points * COALESCE(a.on_time, 0))),
               COALESCE(max(o.score), sum(i.points * GREATEST(COALESCE(a.on_time, 0), COALESCE(a.late, 0)))),
               sum(i.points),
               COALESCE(bool_or(a.tried_on_time), false),
               COALESCE(bool_or(a.tried_late), false),
               bool_and(now() > i.due_at)
        FROM students st CROSS JOIN items i
        LEFT JOIN attempts a ON a.assignment_id = i.assignment_id AND a.kind = i.kind AND a.ref_id = i.ref_id
                             AND a.user_id = st.id
        LEFT JOIN score_overrides o ON o.assignment_id = i.assignment_id AND o.user_id = st.id
        WHERE NOT EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = i.assignment_id)
           OR EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = i.assignment_id AND g.user_id = st.id)
        GROUP BY st.id, i.assignment_id
    $$;
"""


def upgrade() -> None:
    op.execute("""
    CREATE TABLE grade_categories (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
        weight double precision NOT NULL CHECK (weight > 0 AND weight <= 100),
        position integer NOT NULL DEFAULT 0,
        UNIQUE (course_id, name)
    );
    ALTER TABLE assignments ADD COLUMN category_id integer REFERENCES grade_categories(id) ON DELETE SET NULL;

    CREATE TABLE score_overrides (
        assignment_id integer NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
        user_id integer NOT NULL REFERENCES users(id),
        score double precision NOT NULL CHECK (score >= 0),
        reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
        set_by integer NOT NULL REFERENCES users(id),
        set_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (assignment_id, user_id)
    );

    CREATE TABLE rubrics (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE rubric_criteria (
        id serial PRIMARY KEY,
        rubric_id integer NOT NULL REFERENCES rubrics(id) ON DELETE CASCADE,
        position integer NOT NULL,
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        description text CHECK (description IS NULL OR length(description) <= 1000)
    );
    CREATE TABLE rubric_levels (
        id serial PRIMARY KEY,
        criterion_id integer NOT NULL REFERENCES rubric_criteria(id) ON DELETE CASCADE,
        position integer NOT NULL,
        label text NOT NULL CHECK (length(label) BETWEEN 1 AND 100),
        points double precision NOT NULL CHECK (points >= 0 AND points <= 100)
    );
    ALTER TABLE assignment_work ADD COLUMN rubric_id integer REFERENCES rubrics(id);
    CREATE TABLE work_rubric_scores (
        submission_id integer NOT NULL REFERENCES work_submissions(id) ON DELETE CASCADE,
        criterion_id integer NOT NULL REFERENCES rubric_criteria(id),
        level_id integer NOT NULL REFERENCES rubric_levels(id),
        PRIMARY KEY (submission_id, criterion_id)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON grade_categories, score_overrides, rubrics, rubric_criteria,
        rubric_levels, work_rubric_scores TO lms_api;
    GRANT USAGE ON SEQUENCE grade_categories_id_seq, rubrics_id_seq, rubric_criteria_id_seq,
        rubric_levels_id_seq TO lms_api;
    """)
    op.execute(_AFTER)


def downgrade() -> None:
    op.execute(_BEFORE)
    op.execute("""
    DROP TABLE work_rubric_scores;
    ALTER TABLE assignment_work DROP COLUMN rubric_id;
    DROP TABLE rubric_levels;
    DROP TABLE rubric_criteria;
    DROP TABLE rubrics;
    DROP TABLE score_overrides;
    ALTER TABLE assignments DROP COLUMN category_id;
    DROP TABLE grade_categories;
    """)
