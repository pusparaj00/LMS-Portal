"""Erasure requests and the mastery erase function (TR-S-07).

A request is pending for 48 hours (the notice period) before it runs, and is kept afterwards as an audit record with
only the user number and dates. user_id has no foreign key because the user row is deleted by the erasure.

mastery, mastery_events and misconception_state stay without a DELETE grant for every role. The mastery role may call
one function that removes a single user's rows from those three tables, so it remains the only role that writes them.

Revision ID: 0009
"""
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE erasure_requests (
        id serial PRIMARY KEY,
        user_id integer NOT NULL,
        kind text NOT NULL CHECK (kind IN ('requested', 'retention')),
        status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'cancelled', 'done')),
        notified_at timestamptz NOT NULL DEFAULT now(),
        due_at timestamptz NOT NULL,
        completed_at timestamptz,
        CHECK (due_at >= notified_at + interval '48 hours')
    );
    CREATE UNIQUE INDEX erasure_one_pending ON erasure_requests (user_id) WHERE status = 'pending';
    GRANT SELECT, INSERT, UPDATE ON erasure_requests TO lms_api;
    GRANT USAGE ON SEQUENCE erasure_requests_id_seq TO lms_api;
    GRANT DELETE ON explanation_cache, consents TO lms_api;

    CREATE FUNCTION erase_user_mastery(target integer) RETURNS integer
    LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        WITH m AS (DELETE FROM mastery WHERE user_id = target RETURNING 1),
             s AS (DELETE FROM misconception_state WHERE user_id = target RETURNING 1),
             e AS (DELETE FROM mastery_events WHERE user_id = target RETURNING 1)
        SELECT ((SELECT count(*) FROM m) + (SELECT count(*) FROM s) + (SELECT count(*) FROM e))::integer
    $$;
    REVOKE ALL ON FUNCTION erase_user_mastery(integer) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION erase_user_mastery(integer) TO lms_mastery;
    """)


def downgrade() -> None:
    op.execute("""
    DROP FUNCTION erase_user_mastery(integer);
    REVOKE DELETE ON explanation_cache, consents FROM lms_api;
    DROP TABLE erasure_requests;
    """)
