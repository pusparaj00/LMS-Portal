"""Archiving courses and problems (F-02).

Submissions, the mastery ledger, assignments and stored explanations all point at problems, so a problem students have
used is archived instead of deleted: it disappears for students and from every selection, and its history stays. A
course is archived the same way. Both can be restored.

Revision ID: 0015
"""
from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE courses ADD COLUMN archived_at timestamptz;
    ALTER TABLE problems ADD COLUMN archived_at timestamptz;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE problems DROP COLUMN archived_at;
    ALTER TABLE courses DROP COLUMN archived_at;
    """)
