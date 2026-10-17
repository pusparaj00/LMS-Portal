"""F-45, F-42, F-20: which worked examples each student has been shown, so a problem whose solution a student has seen
is never used to measure them as a probe or a placement item.

Revision ID: 0020
Revises: 0019
"""
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE worked_examples_seen (
        user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        problem_id integer NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
        shown_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, problem_id)
    );
    GRANT SELECT, INSERT, DELETE ON worked_examples_seen TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE worked_examples_seen")
