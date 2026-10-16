"""LTI 1.3 launch (TR-A-09, F-70): registered platforms, and which course and account each launch maps to.

A platform is identified by its issuer and the client id it gave this tool. A context (a course in the LMS) maps to
one course here; a platform user (`sub`, an opaque id) maps to one account. No name or email from the LMS is stored.

Revision ID: 0011
"""
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE lti_platforms (
        id serial PRIMARY KEY,
        issuer text NOT NULL,
        client_id text NOT NULL,
        auth_login_url text NOT NULL,
        jwks_url text NOT NULL,
        deployment_ids text[] NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (issuer, client_id)
    );
    CREATE TABLE lti_contexts (
        platform_id integer NOT NULL REFERENCES lti_platforms(id),
        context_id text NOT NULL,
        course_id integer NOT NULL REFERENCES courses(id),
        PRIMARY KEY (platform_id, context_id)
    );
    CREATE TABLE lti_users (
        platform_id integer NOT NULL REFERENCES lti_platforms(id),
        sub text NOT NULL,
        user_id integer NOT NULL UNIQUE REFERENCES users(id),
        PRIMARY KEY (platform_id, sub)
    );
    GRANT SELECT, INSERT, UPDATE ON lti_platforms TO lms_api;
    GRANT USAGE ON SEQUENCE lti_platforms_id_seq TO lms_api;
    GRANT SELECT, INSERT ON lti_contexts TO lms_api;
    GRANT SELECT, INSERT, DELETE ON lti_users TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE lti_users; DROP TABLE lti_contexts; DROP TABLE lti_platforms;")
