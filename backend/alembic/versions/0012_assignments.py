"""Assignments with due dates (F-04).

An assignment is a set of the course's coding problems, each worth some points, with a due date. There is no grades
table: scores are computed from the stored run results whenever they are read, so they cannot go stale, and erasing a
student's submissions removes their scores too.

Revision ID: 0012
"""
from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE assignments (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        due_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX assignments_course ON assignments (course_id, due_at);
    CREATE TABLE assignment_problems (
        assignment_id integer NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
        problem_id integer NOT NULL REFERENCES problems(id),
        points double precision NOT NULL DEFAULT 1 CHECK (points > 0 AND points <= 100),
        PRIMARY KEY (assignment_id, problem_id)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON assignments, assignment_problems TO lms_api;
    GRANT USAGE ON SEQUENCE assignments_id_seq TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE assignment_problems; DROP TABLE assignments;")
