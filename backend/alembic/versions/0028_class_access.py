"""Class code, co-teachers, muting and course details (F-81, F-82, F-83).

Every course gets a join code (a database trigger fills it, so every way of creating a course is covered). The owner of
a course is also a row in course_teachers, kept in sync by a trigger; co-teachers are added to the same table.

Revision ID: 0028
Revises: 0027
"""
from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE courses
        ADD COLUMN join_code text,
        ADD COLUMN join_enabled boolean NOT NULL DEFAULT true,
        ADD COLUMN section text CHECK (section IS NULL OR length(section) BETWEEN 1 AND 100),
        ADD COLUMN subject text CHECK (subject IS NULL OR length(subject) BETWEEN 1 AND 100),
        ADD COLUMN color text CHECK (color IS NULL OR color ~ '^#[0-9a-f]{6}$');
    UPDATE courses SET join_code = upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10));
    ALTER TABLE courses ALTER COLUMN join_code SET NOT NULL;
    ALTER TABLE courses ADD CONSTRAINT courses_join_code_shape CHECK (join_code ~ '^[0-9A-Z]{10}$');
    CREATE UNIQUE INDEX courses_join_code ON courses (join_code);

    CREATE TABLE course_teachers (
        course_id integer NOT NULL REFERENCES courses(id),
        user_id integer NOT NULL REFERENCES users(id),
        added_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (course_id, user_id)
    );
    CREATE INDEX course_teachers_user ON course_teachers (user_id);
    INSERT INTO course_teachers (course_id, user_id) SELECT id, instructor_id FROM courses;

    CREATE FUNCTION courses_before_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.join_code IS NULL THEN
            NEW.join_code := upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10));
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER courses_join_code BEFORE INSERT ON courses
        FOR EACH ROW EXECUTE FUNCTION courses_before_insert();
    CREATE FUNCTION courses_after_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        INSERT INTO course_teachers (course_id, user_id) VALUES (NEW.id, NEW.instructor_id) ON CONFLICT DO NOTHING;
        RETURN NEW;
    END $$;
    CREATE TRIGGER courses_owner_teaches AFTER INSERT ON courses
        FOR EACH ROW EXECUTE FUNCTION courses_after_insert();

    ALTER TABLE enrollments ADD COLUMN comments_muted boolean NOT NULL DEFAULT false;
    GRANT SELECT, INSERT, UPDATE, DELETE ON course_teachers TO lms_api;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE enrollments DROP COLUMN comments_muted;
    DROP TRIGGER courses_owner_teaches ON courses;
    DROP FUNCTION courses_after_insert();
    DROP TRIGGER courses_join_code ON courses;
    DROP FUNCTION courses_before_insert();
    DROP TABLE course_teachers;
    DROP INDEX courses_join_code;
    ALTER TABLE courses DROP CONSTRAINT courses_join_code_shape;
    ALTER TABLE courses DROP COLUMN color, DROP COLUMN subject, DROP COLUMN section, DROP COLUMN join_enabled,
        DROP COLUMN join_code;
    """)
