from dataclasses import dataclass

from app.sandbox import RunOutcome, run_batch


@dataclass(frozen=True)
class TestSpec:
    __test__ = False

    id: int | None
    input: str
    expected: str
    hidden: bool
    category: str


@dataclass(frozen=True)
class TestOutcome:
    __test__ = False

    test: TestSpec
    passed: bool
    run: RunOutcome


@dataclass(frozen=True)
class Grade:
    status: str
    passed: int
    failed: int
    error_type: str | None
    failed_categories: list[str]
    runtime_ms: int
    stderr: str | None
    outcomes: list[TestOutcome]

    @property
    def failed_test_ids(self) -> list[int]:
        return [o.test.id for o in self.outcomes if not o.passed and o.test.id is not None]


def normalise(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.rstrip().splitlines())


def grade(code: str, tests: list[TestSpec]) -> Grade:
    runs = run_batch(code, [t.input for t in tests])
    outcomes = [
        TestOutcome(t, r.status == "ok" and normalise(r.stdout) == normalise(t.expected), r)
        for t, r in zip(tests, runs, strict=True)
    ]
    failed = [o for o in outcomes if not o.passed]
    errors = [o.run for o in failed if o.run.status != "ok"]
    error_type = errors[0].status if errors else None
    all_syntax = bool(runs) and all(r.status == "syntax_error" for r in runs)
    status = "passed" if not failed else "error" if all_syntax else "failed"
    return Grade(
        status=status,
        passed=len(outcomes) - len(failed),
        failed=len(failed),
        error_type=error_type,
        failed_categories=sorted({o.test.category for o in failed}),
        runtime_ms=sum(r.runtime_ms for r in runs),
        stderr=errors[0].stderr if errors else None,
        outcomes=outcomes,
    )
