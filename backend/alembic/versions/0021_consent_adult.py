"""TR-S-10: a student confirms they are 18 or older when they agree to the privacy notice.

Revision ID: 0021
Revises: 0020
"""
from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade() -> None:
    op.execute("ALTER TABLE consents ADD COLUMN adult_confirmed boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE consents DROP COLUMN adult_confirmed")
