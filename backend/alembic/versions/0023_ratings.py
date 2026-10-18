"""Course and instructor ratings (F-65): one rating per enrolled student per course.

Revision ID: 0023
Revises: 0022
"""
from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE ratings (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        user_id integer NOT NULL REFERENCES users(id),
        course_rating integer NOT NULL CHECK (course_rating BETWEEN 1 AND 5),
        instructor_rating integer NOT NULL CHECK (instructor_rating BETWEEN 1 AND 5),
        review text CHECK (review IS NULL OR length(review) BETWEEN 1 AND 1000),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz,
        UNIQUE (course_id, user_id)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON ratings TO lms_api;
    GRANT USAGE ON SEQUENCE ratings_id_seq TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE ratings")
