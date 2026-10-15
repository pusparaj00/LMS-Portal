"""Execution core: reference solutions, review status, misconceptions, item options (F-24, TR-D-03).

Revision ID: 0002
"""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE problems
        ADD COLUMN kind text NOT NULL DEFAULT 'code' CHECK (kind IN ('code', 'mcq')),
        ADD COLUMN reference_solution text,
        ADD COLUMN review_status text NOT NULL DEFAULT 'needs human review'
            CHECK (review_status IN ('needs human review', 'reviewed')),
        ADD CONSTRAINT problems_course_title_key UNIQUE (course_id, title);
    ALTER TABLE run_results ADD COLUMN failed_categories text[] NOT NULL DEFAULT '{}';
    CREATE TABLE misconceptions (
        id serial PRIMARY KEY,
        concept_id integer NOT NULL REFERENCES concepts(id),
        name text NOT NULL UNIQUE,
        description text NOT NULL
    );
    CREATE TABLE item_options (
        id serial PRIMARY KEY,
        problem_id integer NOT NULL REFERENCES problems(id),
        option_text text NOT NULL,
        is_correct boolean NOT NULL,
        misconception_id integer REFERENCES misconceptions(id),
        CHECK (is_correct OR misconception_id IS NOT NULL)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON misconceptions, item_options TO lms_api;
    GRANT SELECT ON misconceptions, item_options TO lms_mastery;
    GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO lms_api, lms_mastery;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE item_options, misconceptions;
    ALTER TABLE run_results DROP COLUMN failed_categories;
    ALTER TABLE problems
        DROP CONSTRAINT problems_course_title_key,
        DROP COLUMN review_status, DROP COLUMN reference_solution, DROP COLUMN kind;
    """)
