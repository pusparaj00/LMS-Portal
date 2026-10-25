"""Load the evidence for one failed submission."""
from dataclasses import dataclass

from sqlalchemy import Connection, text

from app.feedback import leak
from app.feedback.verifier import FailedTest
from app.mastery.plan import linked_concepts


@dataclass(frozen=True)
class ExplainContext:
    submission_id: int
    user_id: int
    problem_id: int
    course_id: int
    problem_title: str
    statement: str
    code: str
    reference_solution: str
    status: str
    error_type: str | None
    stderr: str
    failed_categories: list[str]
    failed_tests: list[FailedTest]
    error_concept_ids: frozenset[int]
    concepts: dict[int, str]  # every concept an explanation may legitimately name
    primary_concept_id: int | None
    hidden_inputs: frozenset[str] = frozenset()
    leak_threshold: float = 0.7  # the problem's leak policy, or the tuned default (F-62)
    language: str = "python"  # the problem's language

    @property
    def primary_concept_name(self) -> str | None:
        return self.concepts.get(self.primary_concept_id) if self.primary_concept_id else None

    @property
    def retrieval_query(self) -> str:
        """What to look up in the course notes: the concept plus what went wrong."""
        last_error_line = (self.stderr.strip().splitlines() or [""])[-1][:160]
        categories = ", ".join(c.replace("_", " ") for c in self.failed_categories)
        parts = [
            self.primary_concept_name or "", self.problem_title, categories, self.error_type or "", last_error_line
        ]
        return ". ".join(p.replace("_", " ") for p in parts if p)


class NotExplainable(Exception):
    """The submission does not exist, is not the caller's, or did not fail."""


def load_context(conn: Connection, submission_id: int, user_id: int) -> ExplainContext:
    row = conn.execute(
        text(
            "SELECT s.user_id, s.problem_id, s.code, p.course_id, p.title, p.statement, p.reference_solution,"
            " p.leak_threshold, p.language,"
            " r.status, r.error_type, r.stderr, r.failed_categories, r.failed_test_ids"
            " FROM submissions s JOIN problems p ON p.id = s.problem_id"
            " JOIN run_results r ON r.submission_id = s.id WHERE s.id = :s"
        ),
        {"s": submission_id},
    ).first()
    if row is None or row.user_id != user_id:
        raise NotExplainable("submission not found")
    if row.status == "passed":
        raise NotExplainable("this submission passed, so there is nothing to explain")

    problem = dict(
        conn.execute(
            text("SELECT concept_id, weight FROM problem_concepts WHERE problem_id = :p"), {"p": row.problem_id}
        ).all()
    )
    map_rows = [
        tuple(r)
        for r in conn.execute(
            text(
                "SELECT test_category, error_type, concept_id, weight FROM evidence_concept_map"
                " WHERE concept_id IN (SELECT id FROM concepts WHERE course_id = :c)"
            ),
            {"c": row.course_id},
        )
    ]
    tests = conn.execute(
        text("SELECT id, input, expected, hidden, category FROM test_cases WHERE id = ANY(:ids) ORDER BY id"),
        {"ids": list(row.failed_test_ids)},
    ).all()
    failed_tests = [
        FailedTest(
            t.id, t.category, t.hidden, t.input, t.expected,
            frozenset(linked_concepts(map_rows, problem, t.category, "*")),
        )
        for t in tests
    ]
    error_concepts = (
        frozenset(linked_concepts(map_rows, problem, "*", row.error_type)) if row.error_type else frozenset()
    )

    hidden_inputs = frozenset(
        conn.execute(
            text("SELECT input FROM test_cases WHERE problem_id = :p AND hidden"), {"p": row.problem_id}
        ).scalars()
    )
    candidate_ids = set(problem) | set(error_concepts).union(*(t.concept_ids for t in failed_tests))
    names = dict(
        conn.execute(text("SELECT id, name FROM concepts WHERE id = ANY(:ids)"), {"ids": list(candidate_ids)}).all()
    )
    first = failed_tests[0].concept_ids if failed_tests else error_concepts or frozenset(problem)
    primary = max(first, key=lambda c: problem.get(c, 0.0), default=None)
    return ExplainContext(
        submission_id=submission_id, user_id=user_id, problem_id=row.problem_id, course_id=row.course_id,
        problem_title=row.title, statement=row.statement, code=row.code,
        reference_solution=row.reference_solution or "", status=row.status, error_type=row.error_type,
        stderr=row.stderr or "", failed_categories=list(row.failed_categories), failed_tests=failed_tests,
        error_concept_ids=error_concepts, concepts=names, primary_concept_id=primary,
        hidden_inputs=hidden_inputs,
        leak_threshold=row.leak_threshold if row.leak_threshold is not None else leak.SIMILARITY_THRESHOLD,
        language=row.language or "python",
    )
