"""LTI grade passback (Assignment and Grade Services; TR-A-09, F-04).

A platform's token endpoint, the grade service each LMS course offered at its last launch, and the LMS grade column
made for each assignment. Deleting an assignment forgets its column here; the column in the LMS is left alone.

Revision ID: 0013
"""
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE lti_platforms ADD COLUMN token_url text;
    ALTER TABLE lti_contexts
        ADD COLUMN ags_lineitems text,
        ADD COLUMN ags_scopes text[] NOT NULL DEFAULT '{}';
    GRANT UPDATE ON lti_contexts TO lms_api;
    CREATE TABLE lti_line_items (
        platform_id integer NOT NULL,
        context_id text NOT NULL,
        assignment_id integer NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
        lineitem_url text NOT NULL,
        score_maximum double precision NOT NULL,
        PRIMARY KEY (platform_id, context_id, assignment_id),
        FOREIGN KEY (platform_id, context_id) REFERENCES lti_contexts(platform_id, context_id)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON lti_line_items TO lms_api;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE lti_line_items;
    REVOKE UPDATE ON lti_contexts FROM lms_api;
    ALTER TABLE lti_contexts DROP COLUMN ags_scopes, DROP COLUMN ags_lineitems;
    ALTER TABLE lti_platforms DROP COLUMN token_url;
    """)
