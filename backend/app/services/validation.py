"""Problem validation (TR-D-04, TR-V-02), shared by the import script and POST /problems."""
from app.grading import TestSpec, grade, normalise
from app.sandbox import run_batch


def validate_code_problem(
    *,
    concept_names: list[str],
    known_concepts: set[str],
    reference_solution: str,
    tests: list[dict],
) -> list[str]:
    errors = []
    if not concept_names:
        errors.append("has no concept")
    errors += [f"unknown concept '{c}'" for c in concept_names if c not in known_concepts]
    if not tests:
        errors.append("has no tests")
    errors += [f"test {i} has no category" for i, t in enumerate(tests) if not t.get("category")]
    if errors or not reference_solution.strip():
        return errors or ["has no reference solution"]

    result = grade(
        reference_solution,
        [TestSpec(None, t["input"], t["expected"], t["hidden"], t["category"]) for t in tests],
    )
    for i, outcome in enumerate(result.outcomes):
        if not outcome.passed:
            errors.append(
                f"reference solution fails test {i} ({outcome.test.category}): {outcome.run.status}"
            )
    return errors


def validate_mcq_item(
    *, concept_names: list[str], known_concepts: set[str], options: list[dict],
    known_misconceptions: set[str], code: str,
) -> list[str]:
    errors = []
    if not concept_names:
        errors.append("has no concept")
    errors += [f"unknown concept '{c}'" for c in concept_names if c not in known_concepts]
    if len(options) < 3:
        errors.append("needs at least 3 options")
    if sum(1 for o in options if o["correct"]) != 1:
        errors.append("needs exactly one correct option")
    for o in options:
        if o["correct"]:
            continue
        if not o.get("misconception"):
            errors.append(f"wrong option '{o['text']}' has no misconception")
        elif o["misconception"] not in known_misconceptions:
            errors.append(f"unknown misconception '{o['misconception']}'")

    correct = [o["text"] for o in options if o["correct"]]
    if not errors and len(correct) == 1:
        (run,) = run_batch(code, [""])
        if run.status != "ok":
            errors.append(f"code does not run: {run.status}")
        elif normalise(run.stdout) != normalise(correct[0]):
            errors.append("the correct option is not what the code prints")
    return errors
