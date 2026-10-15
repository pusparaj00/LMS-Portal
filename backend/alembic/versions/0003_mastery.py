"""Mastery service tables, ledger columns and misconception state (TR-M-01, TR-M-02, TR-M-04, TR-M-07, TR-M-09).

Revision ID: 0003
"""
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE concepts
        ADD COLUMN prior double precision NOT NULL DEFAULT 0.5 CHECK (prior BETWEEN 0 AND 1);

    CREATE TABLE mastery_params (
        concept_id integer NOT NULL REFERENCES concepts(id),
        evidence_type text NOT NULL,
        slip double precision NOT NULL CHECK (slip BETWEEN 0 AND 1),
        guess double precision NOT NULL CHECK (guess BETWEEN 0 AND 1),
        CHECK (slip + guess < 1),
        PRIMARY KEY (concept_id, evidence_type)
    );

    -- '*' matches any category or any error type. A failed category or error type changes only
    -- the concepts linked to it here; with no matching row the problem's own concepts are used.
    CREATE TABLE evidence_concept_map (
        test_category text NOT NULL,
        error_type text NOT NULL,
        concept_id integer NOT NULL REFERENCES concepts(id),
        weight double precision NOT NULL CHECK (weight > 0),
        PRIMARY KEY (test_category, error_type, concept_id)
    );

    CREATE TABLE misconception_state (
        user_id integer NOT NULL REFERENCES users(id),
        misconception_id integer NOT NULL REFERENCES misconceptions(id),
        probability double precision NOT NULL CHECK (probability BETWEEN 0 AND 1),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, misconception_id)
    );

    ALTER TABLE mastery_events
        ADD COLUMN weight double precision NOT NULL DEFAULT 1,
        ADD COLUMN correct boolean,
        ADD COLUMN source_event_id bigint REFERENCES mastery_events(id);
    -- One update per piece of evidence, rule and concept: repeated requests change nothing.
    CREATE UNIQUE INDEX mastery_events_once ON mastery_events (user_id, concept_id, rule_id, evidence_ref);

    GRANT SELECT, INSERT, UPDATE, DELETE ON mastery_params, evidence_concept_map TO lms_api;
    GRANT SELECT ON mastery_params, evidence_concept_map TO lms_mastery;
    GRANT SELECT ON misconception_state TO lms_api;
    GRANT SELECT, INSERT, UPDATE ON misconception_state TO lms_mastery;
    GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO lms_api, lms_mastery;
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX mastery_events_once;
    ALTER TABLE mastery_events DROP COLUMN source_event_id, DROP COLUMN correct, DROP COLUMN weight;
    DROP TABLE misconception_state, evidence_concept_map, mastery_params;
    ALTER TABLE concepts DROP COLUMN prior;
    """)
