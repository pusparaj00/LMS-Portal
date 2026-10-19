"""The recommendation rule that puts a weak prerequisite first, shared by the dashboard and the assistant (F-29, TR-M-17).

next_step walks the student's concepts from the weakest up. If a concept builds on prerequisites (concepts.parent_ids,
at any depth) that the student has not mastered (below 0.5), the weakest of those that still has an unsolved problem is
recommended instead, and the concept that needs it is returned as the reason.

Revision ID: 0032
Revises: 0031
"""
from alembic import op

revision = "0032"
down_revision = "0031"


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION next_step(p_user integer, p_course integer)
    RETURNS TABLE (
        concept_id integer, concept text, p double precision, problem_id integer, title text,
        because_id integer, because text, because_p double precision)
    LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE
        c record;
        anc record;
        pick record;
    BEGIN
        FOR c IN
            SELECT k.id, k.name, COALESCE(m.p_known, k.prior) AS p
            FROM concepts k LEFT JOIN mastery m ON m.concept_id = k.id AND m.user_id = p_user
            WHERE k.course_id = p_course ORDER BY 3, k.id
        LOOP
            FOR anc IN
                WITH RECURSIVE up(id) AS (
                    SELECT unnest(parent_ids) FROM concepts WHERE id = c.id
                    UNION
                    SELECT unnest(x.parent_ids) FROM concepts x JOIN up ON x.id = up.id
                )
                SELECT k.id, k.name, COALESCE(m.p_known, k.prior) AS p
                FROM up JOIN concepts k ON k.id = up.id
                LEFT JOIN mastery m ON m.concept_id = k.id AND m.user_id = p_user
                WHERE k.course_id = p_course AND COALESCE(m.p_known, k.prior) < 0.5
                ORDER BY 3, k.id
            LOOP
                SELECT * INTO pick FROM next_problem(p_user, p_course, anc.id);
                IF FOUND THEN
                    RETURN QUERY SELECT anc.id, anc.name, anc.p, pick.problem_id, pick.title, c.id, c.name, c.p;
                    RETURN;
                END IF;
            END LOOP;
            SELECT * INTO pick FROM next_problem(p_user, p_course, c.id);
            IF FOUND THEN
                RETURN QUERY SELECT c.id, c.name, c.p, pick.problem_id, pick.title,
                                    NULL::integer, NULL::text, NULL::double precision;
                RETURN;
            END IF;
        END LOOP;
    END
    $$;

    REVOKE ALL ON FUNCTION next_step(integer, integer) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION next_step(integer, integer) TO lms_api, lms_chat;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION next_step(integer, integer);")
