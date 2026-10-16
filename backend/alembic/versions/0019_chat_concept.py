"""TR-M-08: a chat question is stored with the concept it is about, for later use as a mastery signal.

Revision ID: 0019
Revises: 0018
"""
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE chat_messages ADD COLUMN concept_id integer REFERENCES concepts(id);
    CREATE INDEX chat_messages_concept ON chat_messages (concept_id) WHERE concept_id IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE chat_messages DROP COLUMN concept_id")
