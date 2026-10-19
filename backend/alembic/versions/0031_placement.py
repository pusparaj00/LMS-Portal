"""Placement test background and ability-based estimates (F-26, F-28, TR-M-15).

enrollments.background is the student's own answer about their experience in the course; it only sets the starting
difficulty of the placement test. mastery_events.evidence_value is the value an ability-based estimate moves a concept
towards, so that ledger row can be replayed (TR-M-09).

Revision ID: 0031
Revises: 0030
"""
from alembic import op

revision = "0031"
down_revision = "0030"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE enrollments
        ADD COLUMN background text CHECK (background IS NULL OR background IN ('new', 'some', 'comfortable'));
    ALTER TABLE mastery_events
        ADD COLUMN evidence_value double precision CHECK (evidence_value IS NULL OR (evidence_value >= 0 AND evidence_value <= 1));
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE mastery_events DROP COLUMN evidence_value;
    ALTER TABLE enrollments DROP COLUMN background;
    """)
