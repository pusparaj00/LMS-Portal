"""Profile building (F-01): a learner's past academic history and areas of interest.

Revision ID: 0022
Revises: 0021
"""
from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE users
        ADD COLUMN academic_history text
            CHECK (academic_history IS NULL OR length(academic_history) BETWEEN 1 AND 1000),
        ADD COLUMN interests text
            CHECK (interests IS NULL OR length(interests) BETWEEN 1 AND 500);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN interests, DROP COLUMN academic_history")
