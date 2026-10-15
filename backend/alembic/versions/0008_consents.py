"""Consent records (TR-S-05): which privacy notice a student accepted, when, and when they withdrew.

The newest row for a student is the current state. A new notice version needs a new acceptance.

Revision ID: 0008
"""
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE consents (
        id serial PRIMARY KEY,
        user_id integer NOT NULL REFERENCES users(id),
        version text NOT NULL,
        accepted_at timestamptz NOT NULL DEFAULT now(),
        withdrawn_at timestamptz
    );
    CREATE INDEX consents_user_idx ON consents (user_id, id DESC);
    GRANT SELECT, INSERT, UPDATE ON consents TO lms_api;
    GRANT USAGE ON SEQUENCE consents_id_seq TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE consents")
