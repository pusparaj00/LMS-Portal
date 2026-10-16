"""Account management (F-01, TR-S-01): display names, disabled accounts, forced password changes, and the moment
credentials last changed, so sign-in tokens issued before it stop working.

credentials_changed_at is empty until a password is changed, reset or the account disabled, so this migration signs
nobody out.

Revision ID: 0016
"""
from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE users
        ADD COLUMN display_name text CHECK (display_name IS NULL OR length(display_name) BETWEEN 1 AND 80),
        ADD COLUMN disabled_at timestamptz,
        ADD COLUMN must_change_password boolean NOT NULL DEFAULT false,
        ADD COLUMN credentials_changed_at timestamptz;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE users
        DROP COLUMN credentials_changed_at, DROP COLUMN must_change_password, DROP COLUMN disabled_at,
        DROP COLUMN display_name;
    """)
