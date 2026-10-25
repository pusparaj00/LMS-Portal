"""TR-V-13: for Java and C, every reference solution passes and a deliberately wrong version of it fails.

Each wrong solution is the reference with one realistic mistake (`old` replaced by `new`). It must fail at least one
test, and the failing categories must include the one the mistake is about, decided from the mistake itself, not from
a run. Everything runs in the sandbox. Usage, inside the api or test container:
    python -m evaluation.wrong_solutions_compiled /path/to/data/bank
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.grading import TestSpec, grade

# language -> problem title -> (text in the reference, replacement, category the mistake should trip)
MISTAKES = {
    "java": {
        "Sum of the numbers": ("i < n", "i < n - 1", "basic"),  # skips the last number
        "The largest number": ("Integer.MIN_VALUE", "0", "boundary"),  # all-negative input
        "Rectangle area": ("width * height", "width + height", "basic"),
        "Bank account": ("amount <= balance", "amount < balance", "basic"),  # cannot empty the account
        "Largest in a list": ("int best = values.get(0);", "int best = 0;", "basic"),
        "Distinct values": ("seen.size()", "n", "basic"),  # counts every value
        "The larger one": ("x > y ? x : y", "x < y ? x : y", "basic"),
        "Divisible by four": ("n % 4 == 0", "n % 2 == 0", "basic"),
        "Safe parse": ("NumberFormatException", "ArithmeticException", "invalid_token"),  # wrong exception caught
        "Safe division": ("ArithmeticException", "NumberFormatException", "invalid_token"),
        "Double it": ("x * 2", "x + 2", "basic"),
        "Sum from 1 to n": ("i <= n", "i < n", "basic"),
        "Count the evens": ("i % 2 == 0", "i % 2 == 1", "basic"),
        "Factorial, recursively": ("n <= 1 ? 1", "n <= 1 ? 0", "basic"),
        "How long is it": ("s.length()", "s.length() - 1", "basic"),
        "First and last": ("s.length() - 1", "s.length()", "basic"),  # reads past the end
        "Sum of two": ("x + y", "x - y", "basic"),
        "Truncated average": ("(x + y) / 2", "(x + y) / 2.0", "basic"),  # prints a fraction
    },
    "c": {
        "Sum of the numbers": ("i < n", "i < n - 1", "basic"),
        "The largest number": ("v > max", "v < max", "basic"),
        "The larger one": ("x > y ? x : y", "x < y ? x : y", "basic"),
        "Divisible by four": ("n % 4 == 0", "n % 2 == 0", "basic"),
        "Double it": ("x * 2", "x + 2", "basic"),
        "Sum from 1 to n": ("i <= n", "i < n", "basic"),
        "Count the evens": ("i % 2 == 0", "i % 2 == 1", "basic"),
        "Dynamic array sum": ("total += v[i]", "total = v[i]", "basic"),
        "Reverse with a pointer": ("p >= v", "p > v", "basic"),  # drops the first element
        "Reach through a pointer": ("p[i]", "p[i + 1]", "basic"),
        "Factorial, recursively": ("n <= 1 ? 1", "n <= 1 ? 0", "basic"),
        "How long is it": ("strlen(s)", "strlen(s) + 1", "basic"),
        "Squared distance": ("dx * dx + dy * dy", "dx + dy", "basic"),
        "Oldest student": ("> s[best].age", ">= s[best].age", "boundary"),  # a tie picks the last student
        "Sum of two": ("x + y", "x - y", "basic"),
        "Truncated average": ("/ 2", "/ 3", "basic"),
    },
}


def specs(problem: dict) -> list[TestSpec]:
    return [TestSpec(None, t["input"], t["expected"], t["hidden"], t["category"]) for t in problem["tests"]]


def main() -> int:
    bank = Path(sys.argv[1])
    lines = [
        f"Run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC on {bank}.",
        "",
        "| Language | Problem | Reference | Wrong solution | Failing categories | Caught as expected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    bad = 0
    for language, mistakes in MISTAKES.items():
        problems = {p["title"]: p for f in sorted((bank / language / "problems").glob("*.json"))
                    for p in json.loads(f.read_text(encoding="utf-8"))}
        for title in sorted(set(problems) | set(mistakes)):
            problem, mistake = problems.get(title), mistakes.get(title)
            if problem is None or mistake is None:
                lines.append(f"| {language} | {title} | - | - | - | NO ({'no mistake written' if mistake is None else 'no problem'}) |")
                bad += 1
                continue
            old, new, expected = mistake
            reference = problem["reference_solution"]
            assert reference.count(old) == 1, (language, title, old)
            right = grade(reference, specs(problem), language)
            wrong = grade(reference.replace(old, new), specs(problem), language)
            caught = right.status == "passed" and wrong.status != "passed" and expected in wrong.failed_categories
            bad += not caught
            lines.append(
                f"| {language} | {title} | {right.status} | {wrong.status} | "
                f"{', '.join(sorted(wrong.failed_categories)) or '-'} | {'yes' if caught else 'NO'} |"
            )
    lines += ["", f"{sum(len(m) for m in MISTAKES.values()) - bad} of {sum(len(m) for m in MISTAKES.values())} caught."]
    print("\n".join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
