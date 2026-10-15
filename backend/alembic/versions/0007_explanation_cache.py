"""Failure-signature cache of verified explanations (F-46, TR-L-09) and instructor review (F-62).

The signature is a hash of the problem, the sorted failed test categories, the error type and the normalised error
message. `line_text` and `test_category` let a stored explanation be checked again against a later submission.

Revision ID: 0007
"""
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE explanation_cache (
        id serial PRIMARY KEY,
        signature text NOT NULL UNIQUE,
        problem_id integer NOT NULL REFERENCES problems(id),
        explanation_json jsonb NOT NULL,
        status text NOT NULL DEFAULT 'auto_verified'
            CHECK (status IN ('auto_verified', 'instructor_approved', 'rejected')),
        hit_count integer NOT NULL DEFAULT 0,
        approved_by integer REFERENCES users(id),
        source_submission_id integer NOT NULL REFERENCES submissions(id),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX explanation_cache_problem_idx ON explanation_cache (problem_id);
    GRANT SELECT, INSERT, UPDATE ON explanation_cache TO lms_api;
    GRANT USAGE ON SEQUENCE explanation_cache_id_seq TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE explanation_cache")
