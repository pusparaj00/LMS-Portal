"""Course language: each course teaches one language (F-94).

A course is taught in exactly one of python, java or c. Problems inherit the course's language, so
adding a column to courses (rather than relying on problems.language alone) makes the language a
first-class, immutable property of the course.

Revision ID: 0034
Revises: 0033
"""
from alembic import op

revision = "0034"
down_revision = "0033"


def upgrade() -> None:
    op.execute("ALTER TABLE courses ADD COLUMN language text NOT NULL DEFAULT 'python'")
    op.execute("ALTER TABLE courses ADD CONSTRAINT courses_language_check CHECK (language IN ('python', 'java', 'c'))")


def downgrade() -> None:
    op.execute("ALTER TABLE courses DROP CONSTRAINT IF EXISTS courses_language_check")
    op.execute("ALTER TABLE courses DROP COLUMN IF EXISTS language")
