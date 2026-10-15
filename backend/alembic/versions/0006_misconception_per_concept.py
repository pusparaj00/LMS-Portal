"""Misconception names are unique per concept, not across the whole database (F-29, F-61).

With a global unique name, importing the bank into a second course moved every misconception to the new course,
so the first course lost its misconception counts and its tracing options pointed at another course's concepts.

Revision ID: 0006
"""
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.execute("ALTER TABLE misconceptions DROP CONSTRAINT misconceptions_name_key")
    op.execute("ALTER TABLE misconceptions ADD CONSTRAINT misconceptions_concept_name_key UNIQUE (concept_id, name)")


def downgrade() -> None:
    op.execute("ALTER TABLE misconceptions DROP CONSTRAINT misconceptions_concept_name_key")
    op.execute("ALTER TABLE misconceptions ADD CONSTRAINT misconceptions_name_key UNIQUE (name)")
