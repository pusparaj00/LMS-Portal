"""Retag stored note vectors for fastembed 0.9.1 (TR-L-02).

The embedding tag includes the fastembed version, and search only reads chunks whose tag equals the running one. Version 0.9.1
(taken to allow Pillow 13) returns the same vectors as 0.9.0 for the same model: compared on 53 texts as queries and as
passages, the largest difference was 0. So existing chunks are retagged and need no re-embedding.

Revision ID: 0035
Revises: 0034
"""
from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade() -> None:
    op.execute(
        "UPDATE chunks SET embedding_model = 'BAAI/bge-small-en-v1.5@fastembed-0.9.1' "
        "WHERE embedding_model = 'BAAI/bge-small-en-v1.5@fastembed-0.9.0'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE chunks SET embedding_model = 'BAAI/bge-small-en-v1.5@fastembed-0.9.0' "
        "WHERE embedding_model = 'BAAI/bge-small-en-v1.5@fastembed-0.9.1'"
    )
