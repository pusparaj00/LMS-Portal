"""Notes the instructor chooses to show to students (F-93).

Notes were only the assistant's source material. A note is now hidden from students until the instructor switches it
on, because notes often hold worked examples and a visible note must not hand out a problem's solution.

Revision ID: 0033
Revises: 0032
"""
from alembic import op

revision = "0033"
down_revision = "0032"


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN visible_to_students boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN visible_to_students")
