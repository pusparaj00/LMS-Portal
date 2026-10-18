"""Course content (F-66, F-67, F-68): modules, lesson items and each student's completions.

Revision ID: 0024
Revises: 0023
"""
from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE modules (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        position integer NOT NULL,
        published boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX modules_course ON modules (course_id, position, id);
    CREATE TABLE content_items (
        id serial PRIMARY KEY,
        module_id integer NOT NULL REFERENCES modules(id),
        kind text NOT NULL CHECK (kind IN ('text', 'link', 'video', 'file')),
        title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
        body text CHECK (body IS NULL OR length(body) BETWEEN 1 AND 20000),
        url text CHECK (url IS NULL OR (length(url) <= 2000 AND url ~ '^https?://[^[:space:]]+$')),
        file_name text CHECK (file_name IS NULL OR length(file_name) BETWEEN 1 AND 200),
        file_data bytea CHECK (file_data IS NULL OR octet_length(file_data) <= 5000000),
        position integer NOT NULL,
        published boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now(),
        CHECK (
            (kind = 'text' AND body IS NOT NULL AND url IS NULL AND file_data IS NULL AND file_name IS NULL)
            OR (kind IN ('link', 'video') AND url IS NOT NULL AND body IS NULL AND file_data IS NULL
                AND file_name IS NULL)
            OR (kind = 'file' AND file_data IS NOT NULL AND file_name IS NOT NULL AND body IS NULL AND url IS NULL)
        )
    );
    CREATE INDEX content_items_module ON content_items (module_id, position, id);
    CREATE TABLE item_completions (
        user_id integer NOT NULL REFERENCES users(id),
        item_id integer NOT NULL REFERENCES content_items(id),
        completed_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, item_id)
    );
    GRANT SELECT, INSERT, UPDATE, DELETE ON modules, content_items, item_completions TO lms_api;
    GRANT USAGE ON SEQUENCE modules_id_seq, content_items_id_seq TO lms_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE item_completions; DROP TABLE content_items; DROP TABLE modules;")
