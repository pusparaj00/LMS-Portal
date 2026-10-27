"""The next problem is the one that fits the student's level on the concept, not the easiest left (F-29, TR-M-17).

next_problem now orders unsolved coding problems on the concept by how close their difficulty is to the difficulty at
which the student would succeed about 7 times in 10: logit(mastery) - logit(0.7), with mastery from the mastery table or
the concept's prior. The placement test uses the same scale. The dashboard and the assistant call this function through
next_step, so they still agree.

Revision ID: 0034
Revises: 0033
"""
from alembic import op

revision = "0034"
down_revision = "0033"


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION next_problem(p_user integer, p_course integer, p_concept integer)
    RETURNS TABLE (problem_id integer, title text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        WITH level AS (
            SELECT LEAST(0.99, GREATEST(0.01, COALESCE(
                (SELECT m.p_known FROM mastery m WHERE m.user_id = p_user AND m.concept_id = p_concept),
                (SELECT k.prior FROM concepts k WHERE k.id = p_concept), 0.5))) AS q
        )
        SELECT p.id, p.title FROM problems p
        JOIN problem_concepts pc ON pc.problem_id = p.id AND pc.concept_id = p_concept
        WHERE p.kind = 'code' AND p.course_id = p_course AND p.archived_at IS NULL AND NOT EXISTS (
            SELECT 1 FROM submissions s JOIN run_results r ON r.submission_id = s.id
            WHERE s.problem_id = p.id AND s.user_id = p_user AND r.status = 'passed')
        ORDER BY abs(p.difficulty_b - (ln((SELECT q FROM level) / (1 - (SELECT q FROM level))) - ln(0.7 / 0.3))), p.id
        LIMIT 1
    $$;
    """)


def downgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION next_problem(p_user integer, p_course integer, p_concept integer)
    RETURNS TABLE (problem_id integer, title text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        SELECT p.id, p.title FROM problems p
        JOIN problem_concepts pc ON pc.problem_id = p.id AND pc.concept_id = p_concept
        WHERE p.kind = 'code' AND p.course_id = p_course AND p.archived_at IS NULL AND NOT EXISTS (
            SELECT 1 FROM submissions s JOIN run_results r ON r.submission_id = s.id
            WHERE s.problem_id = p.id AND s.user_id = p_user AND r.status = 'passed')
        ORDER BY p.difficulty_b, p.id LIMIT 1
    $$;
    """)
