"""Audit trail for breach detection (TR-S-08).

The API role may add and read events but never change or remove them, so a compromised API cannot rewrite its own
trail. Old events are removed only through one function that deletes rows older than a given number of days.
user_id has no foreign key: the trail must outlive an erased account, and holds only its number.

Revision ID: 0010
"""
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE audit_events (
        id bigserial PRIMARY KEY,
        at timestamptz NOT NULL DEFAULT now(),
        event text NOT NULL,
        user_id integer,
        ip text,
        request_id text,
        status integer,
        detail jsonb NOT NULL DEFAULT '{}'
    );
    CREATE INDEX audit_events_at ON audit_events (at);
    CREATE INDEX audit_events_event_at ON audit_events (event, at);
    GRANT SELECT, INSERT ON audit_events TO lms_api;
    GRANT USAGE ON SEQUENCE audit_events_id_seq TO lms_api;

    CREATE FUNCTION purge_audit_events(days integer) RETURNS integer
    LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        WITH gone AS (DELETE FROM audit_events WHERE days > 0 AND at < now() - make_interval(days => days) RETURNING 1)
        SELECT count(*)::integer FROM gone
    $$;
    REVOKE ALL ON FUNCTION purge_audit_events(integer) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION purge_audit_events(integer) TO lms_api;
    """)


def downgrade() -> None:
    op.execute("""
    DROP FUNCTION purge_audit_events(integer);
    DROP TABLE audit_events;
    """)
