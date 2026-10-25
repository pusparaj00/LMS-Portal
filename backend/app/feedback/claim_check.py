"""Check a claimed input in the sandbox (TR-L-05).

When an explanation says the program goes wrong on a specific input, the student's program and the reference solution
are both run on that input in the sandbox, and the explanation is accepted only if their outputs really differ. A claim
that cannot be tried (no reference solution, sandbox unavailable) is not accepted: nothing unverified reaches a student.
"""
from dataclasses import dataclass

from app.feedback.verifier import Check, Evidence, Explanation, all_passed, verify
from app.grading import normalise
from app.sandbox import SandboxUnavailable, run_batch

CHECK_NAME = "claimed_input"
MAX_SHOWN_OUTPUT = 200


@dataclass(frozen=True)
class ExampleRun:
    """What the student may see: the input, and what their own program did with it. Never the reference's output."""

    input: str
    student_output: str


def _shown(outcome) -> str:
    if outcome.status != "ok":
        return f"(no output: the program stopped with a {outcome.status.replace('_', ' ')})"
    text = outcome.stdout.strip()
    return (text[:MAX_SHOWN_OUTPUT] + "...") if len(text) > MAX_SHOWN_OUTPUT else text or "(nothing was printed)"


def run_claim(code: str, reference_solution: str, example_input: str) -> tuple[Check, ExampleRun | None]:
    if not reference_solution.strip():
        return Check(CHECK_NAME, False, "there is no reference solution to compare with"), None
    stdin = example_input if example_input.endswith("\n") else example_input + "\n"
    try:
        (student,) = run_batch(code, [stdin])
        (reference,) = run_batch(reference_solution, [stdin])
    except SandboxUnavailable:
        return Check(CHECK_NAME, False, "the sandbox could not try the example input"), None
    if reference.status != "ok":
        return Check(CHECK_NAME, False, "the correct program does not run on the example input; use a valid one"), None
    if student.status == "ok" and normalise(student.stdout) == normalise(reference.stdout):
        same = "the student's program prints the same output as the correct program on the example input"
        return Check(CHECK_NAME, False, same), None
    return Check(CHECK_NAME, True), ExampleRun(input=example_input.strip("\n"), student_output=_shown(student))


def verify_with_example(raw: str, evidence: Evidence) -> tuple[Explanation | None, list[Check], ExampleRun | None]:
    """The verifier's checks, then, if all pass and the reply names an input, the sandbox check on that input."""
    explanation, checks = verify(raw, evidence)
    example = None
    if explanation is not None and all_passed(checks) and explanation.example_input.strip():
        check, example = run_claim(evidence.code, evidence.reference_solution, explanation.example_input)
        checks.append(check)
    return explanation, checks, example
