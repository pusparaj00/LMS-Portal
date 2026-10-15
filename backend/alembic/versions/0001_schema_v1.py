"""Schema version 1: the 15 core tables of DRD section 3 and the database roles.

Revision ID: 0001
"""
import os

from alembic import op

revision = "0001"
down_revision = None

TABLES_API_WRITES = [
    "users", "courses", "enrollments", "concepts", "problems", "problem_concepts",
    "test_cases", "submissions", "run_results", "diagnostic_sessions", "documents",
    "chunks", "chat_messages",
]
MASTERY_TABLES = ["mastery", "mastery_events"]


def _password(var: str) -> str:
    return "'" + os.environ[var].replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
    CREATE TABLE users (
        id serial PRIMARY KEY,
        email text NOT NULL UNIQUE,
        password_hash text NOT NULL,
        role text NOT NULL CHECK (role IN ('student', 'instructor', 'admin')),
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE courses (
        id serial PRIMARY KEY,
        title text NOT NULL,
        instructor_id integer NOT NULL REFERENCES users(id)
    );
    CREATE TABLE enrollments (
        user_id integer NOT NULL REFERENCES users(id),
        course_id integer NOT NULL REFERENCES courses(id),
        enrolled_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, course_id)
    );
    CREATE TABLE concepts (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        name text NOT NULL,
        parent_ids integer[] NOT NULL DEFAULT '{}',
        UNIQUE (course_id, name)
    );
    CREATE TABLE problems (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        title text NOT NULL,
        statement text NOT NULL,
        language text NOT NULL DEFAULT 'python',
        difficulty_b double precision NOT NULL,
        discrimination_a double precision NOT NULL,
        param_source text NOT NULL DEFAULT 'prior' CHECK (param_source IN ('prior', 'estimated'))
    );
    CREATE TABLE problem_concepts (
        problem_id integer NOT NULL REFERENCES problems(id),
        concept_id integer NOT NULL REFERENCES concepts(id),
        weight double precision NOT NULL,
        PRIMARY KEY (problem_id, concept_id)
    );
    CREATE TABLE test_cases (
        id serial PRIMARY KEY,
        problem_id integer NOT NULL REFERENCES problems(id),
        input text NOT NULL,
        expected text NOT NULL,
        hidden boolean NOT NULL DEFAULT false,
        category text NOT NULL
    );
    CREATE TABLE submissions (
        id serial PRIMARY KEY,
        user_id integer NOT NULL REFERENCES users(id),
        problem_id integer NOT NULL REFERENCES problems(id),
        code text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE run_results (
        submission_id integer PRIMARY KEY REFERENCES submissions(id),
        status text NOT NULL,
        passed integer NOT NULL,
        failed integer NOT NULL,
        error_type text,
        stderr text,
        runtime_ms integer
    );
    CREATE TABLE mastery (
        user_id integer NOT NULL REFERENCES users(id),
        concept_id integer NOT NULL REFERENCES concepts(id),
        p_known double precision NOT NULL CHECK (p_known BETWEEN 0 AND 1),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, concept_id)
    );
    CREATE TABLE mastery_events (
        id bigserial PRIMARY KEY,
        user_id integer NOT NULL REFERENCES users(id),
        concept_id integer NOT NULL REFERENCES concepts(id),
        p_before double precision NOT NULL,
        p_after double precision NOT NULL,
        evidence_type text NOT NULL,
        rule_id text NOT NULL,
        submission_id integer REFERENCES submissions(id),
        evidence_ref text,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE diagnostic_sessions (
        id serial PRIMARY KEY,
        user_id integer NOT NULL REFERENCES users(id),
        state_json jsonb NOT NULL DEFAULT '{}',
        status text NOT NULL DEFAULT 'active'
    );
    CREATE TABLE documents (
        id serial PRIMARY KEY,
        course_id integer NOT NULL REFERENCES courses(id),
        title text NOT NULL,
        source_ref text
    );
    CREATE TABLE chunks (
        id serial PRIMARY KEY,
        document_id integer NOT NULL REFERENCES documents(id),
        text text NOT NULL,
        embedding vector,
        embedding_model text,
        source_ref text
    );
    CREATE TABLE chat_messages (
        id serial PRIMARY KEY,
        user_id integer NOT NULL REFERENCES users(id),
        role text NOT NULL,
        content text NOT NULL,
        route text,
        sources jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    """)

    op.execute(f"CREATE ROLE lms_api LOGIN PASSWORD {_password('LMS_API_DB_PASSWORD')}")
    op.execute(f"CREATE ROLE lms_mastery LOGIN PASSWORD {_password('LMS_MASTERY_DB_PASSWORD')}")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO lms_api, lms_mastery")
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO lms_api, lms_mastery")

    api_writes = ", ".join(TABLES_API_WRITES)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {api_writes} TO lms_api")
    op.execute("GRANT SELECT ON mastery, mastery_events TO lms_api")

    # mastery_events is append-only: the mastery role gets no UPDATE or DELETE on it.
    op.execute(f"GRANT SELECT ON {api_writes} TO lms_mastery")
    op.execute("GRANT SELECT, INSERT, UPDATE ON mastery TO lms_mastery")
    op.execute("GRANT SELECT, INSERT ON mastery_events TO lms_mastery")


def downgrade() -> None:
    op.execute("""
    DROP TABLE chat_messages, chunks, documents, diagnostic_sessions, mastery_events, mastery,
        run_results, submissions, test_cases, problem_concepts, problems, concepts,
        enrollments, courses, users;
    DROP OWNED BY lms_api, lms_mastery;
    DROP ROLE lms_api, lms_mastery;
    """)
