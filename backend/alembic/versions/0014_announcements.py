"""Course announcements (F-05): short plain-text notices from the course's teacher to its students.

Revision ID: 0014
"""
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE announcements (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        author_id integer NOT NULL REFERENCES users(id),
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        body text NOT NULL CHECK (length(body) BETWEEN 1 AND 5000),
        created_at timestamptz NOT NULL DEFAULT now(),
        edited_at timestamptz
    );
    CREATE INDEX announcements_course ON announcements (course_id, created_at DESC);
    GRANT SELECT, INSERT, UPDATE, DELETE ON announcements TO lms_api;
    GRANT USAGE ON SEQUENCE announcements_id_seq TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE announcements")
