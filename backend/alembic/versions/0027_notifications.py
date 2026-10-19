"""In-app notifications (F-80).

Revision ID: 0027
Revises: 0026
"""
from alembic import op

revision = "0027"
down_revision = "0026"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE notifications (
        id serial PRIMARY KEY,
        user_id integer NOT NULL REFERENCES users(id),
        kind text NOT NULL CHECK (kind IN ('announcement', 'work_returned', 'work_turned_in', 'comment', 'due_soon')),
        course_id integer REFERENCES courses(id),
        assignment_id integer REFERENCES assignments(id) ON DELETE CASCADE,
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
        link text NOT NULL CHECK (link ~ '^#/[A-Za-z0-9/_-]*$'),
        created_at timestamptz NOT NULL DEFAULT now(),
        read_at timestamptz
    );
    CREATE INDEX notifications_user ON notifications (user_id, id DESC);
    CREATE INDEX notifications_unread ON notifications (user_id) WHERE read_at IS NULL;
    CREATE UNIQUE INDEX notifications_one_due_soon ON notifications (user_id, assignment_id) WHERE kind = 'due_soon';
    GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO lms_api;
    GRANT USAGE ON SEQUENCE notifications_id_seq TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE notifications;")
