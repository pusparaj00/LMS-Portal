"""A per-problem leak policy (F-62; DRD: PUT /problems/{id}/policy sets "the maximum hint level and leak policy").

A problem may make the leak guard stricter than the threshold tuned on the question bank (0.7, TR-L-06), never looser:
replies never contain a full solution (the project's non-negotiable rule). Empty means the tuned default.

Revision ID: 0018
"""
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE problems ADD COLUMN leak_threshold double precision
        CHECK (leak_threshold IS NULL OR leak_threshold BETWEEN 0.3 AND 0.7);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE problems DROP COLUMN leak_threshold")
