"""Verified feedback loop: notes ingestion, failed test ids, hint policy, explanation_checks.

Revision ID: 0004
"""
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE run_results ADD COLUMN failed_test_ids integer[] NOT NULL DEFAULT '{}';
    ALTER TABLE problems
        ADD COLUMN max_hint_level integer NOT NULL DEFAULT 3 CHECK (max_hint_level BETWEEN 1 AND 3);

    ALTER TABLE documents
        ADD COLUMN body text NOT NULL DEFAULT '',
        ADD COLUMN concept_id integer REFERENCES concepts(id),
        ADD COLUMN content_hash text,
        ADD COLUMN status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'failed')),
        ADD COLUMN status_detail text,
        ADD COLUMN review_status text NOT NULL DEFAULT 'needs human review'
            CHECK (review_status IN ('needs human review', 'reviewed')),
        ADD CONSTRAINT documents_course_source_key UNIQUE (course_id, source_ref);
    ALTER TABLE chunks
        ADD COLUMN chunk_index integer NOT NULL DEFAULT 0,
        ADD COLUMN section text;

    CREATE TABLE explanation_checks (
        id serial PRIMARY KEY,
        submission_id integer NOT NULL REFERENCES submissions(id),
        check_name text NOT NULL,
        passed boolean NOT NULL,
        attempt integer NOT NULL,
        model text,
        prompt_version text,
        detail text,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX explanation_checks_submission ON explanation_checks (submission_id);

    GRANT SELECT, INSERT, UPDATE, DELETE ON explanation_checks TO lms_api;
    GRANT SELECT ON explanation_checks TO lms_mastery;
    GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO lms_api, lms_mastery;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE explanation_checks;
    ALTER TABLE chunks DROP COLUMN section, DROP COLUMN chunk_index;
    ALTER TABLE documents
        DROP CONSTRAINT documents_course_source_key, DROP COLUMN review_status, DROP COLUMN status_detail,
        DROP COLUMN status, DROP COLUMN content_hash, DROP COLUMN concept_id, DROP COLUMN body;
    ALTER TABLE problems DROP COLUMN max_hint_level;
    ALTER TABLE run_results DROP COLUMN failed_test_ids;
    """)
