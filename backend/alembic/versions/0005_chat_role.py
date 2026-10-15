"""Read-only database role for the chat handlers (TR-A-02, TR-L-08).

The chat handlers answer questions about progress. They connect as this role, which can read only
the concept, mastery and enrolment tables, so no handler can write mastery or read another table.

Revision ID: 0005
"""
import os

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    password = os.environ["LMS_CHAT_DB_PASSWORD"].replace("'", "''")
    op.execute(f"CREATE ROLE lms_chat LOGIN PASSWORD '{password}'")
    op.execute("GRANT USAGE ON SCHEMA public TO lms_chat")
    op.execute("GRANT SELECT ON concepts, mastery, enrollments, courses TO lms_chat")


def downgrade() -> None:
    op.execute("DROP OWNED BY lms_chat")
    op.execute("DROP ROLE lms_chat")
