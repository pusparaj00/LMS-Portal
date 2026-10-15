"""Turn run evidence into per-concept updates (DRD section 4 evidence weighting, TR-M-02)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    evidence_type: str
    weight: float
    correct: bool


# (test_category, error_type, concept_id, weight) rows from evidence_concept_map.
# Category rows have error_type '*'; error-type rows have category '*'.
MapRow = tuple[str, str, int, float]


def linked_concepts(rows: list[MapRow], problem: dict[int, float], category: str, error_type: str) -> dict[int, float]:
    """Concepts a failed category or error type points at, or the problem's own concepts."""
    linked = {
        cid: w * problem.get(cid, 1.0)
        for cat, err, cid, w in rows
        if cat == category and err == error_type
    }
    return linked or dict(problem)


def plan_submission(
    *,
    status: str,
    passed: int,
    error_type: str | None,
    failed_categories: list[str],
    problem_concepts: dict[int, float],
    map_rows: list[MapRow],
) -> dict[int, Plan]:
    if status == "passed":
        return {c: Plan("all_pass", w, True) for c, w in problem_concepts.items()}

    if status == "error":  # nothing ran: only the syntax concept is touched
        linked = linked_concepts(map_rows, problem_concepts, "*", "syntax_error")
        return {c: Plan("syntax_error", min(1.0, w), False) for c, w in linked.items()}

    plan: dict[int, Plan] = {}
    evidence = "partial_fail" if passed > 0 else "full_fail"
    for category in failed_categories:
        for c, w in linked_concepts(map_rows, problem_concepts, category, "*").items():
            plan[c] = Plan(evidence, min(1.0, w), False)
    if error_type:  # an error type is stronger evidence than a wrong answer, so it replaces it
        for c, w in linked_concepts(map_rows, problem_concepts, "*", error_type).items():
            plan[c] = Plan(error_type, min(1.0, w), False)
    return plan
