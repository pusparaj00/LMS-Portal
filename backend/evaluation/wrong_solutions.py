"""TR-V-02: every deliberately wrong solution must fail, and fail in the test category its mistake is about.

Runs the rating sheet's wrong solutions against the problems as stored (hidden tests included) in the sandbox and prints
a Markdown table. Usage, inside the api container:
    python -m evaluation.wrong_solutions COURSE_ID
"""
import sys
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import get_engine
from app.grading import TestSpec, grade
from evaluation.rating_sheet import SUBMISSIONS

# The category each mistake should trip, decided from the mistake itself, not from a run.
EXPECTED = {
    "Sum from 1 to n": "basic",  # range(n) stops one short
    "Factorial": "basic",  # starts the product at 0
    "Countdown": "basic",  # range(n, 0) is empty
    "Reverse a string": "basic",  # str has no reverse()
    "Count vowels": "uppercase",  # only lowercase vowels counted
    "Second largest": "duplicates",  # values[-2] repeats the largest
    "Word frequency": "basic",  # counts[w] += 1 on a missing key
    "Fibonacci": "base_case",  # no base case
    "Safe division": "zero_divisor",  # divides by zero
    "Rectangle": "basic",  # area adds instead of multiplying
    "Palindrome check": "uppercase",  # case is not ignored
    "Remove duplicates": "order",  # sorted set loses the first-seen order
    "Grade letter": "boundary",  # > where >= is needed
    "Leap year": "century",  # only the divisible-by-4 rule
    "Digit sum": "base_case",  # no base case
    "Phone book": "missing_key",  # book[name] on a missing name
    "Rotate left": "k_larger_than_n",  # k not reduced modulo n
    "Most common letter": "tie",  # first-seen letter wins a tie
    "Word count": "whitespace",  # split(" ") counts empty strings
    "Even or odd": "basic",  # the two answers swapped
    "Sum and maximum": "basic",  # total = x instead of total += x
}


def tests_for(conn, course_id: int, title: str) -> list[TestSpec]:
    problem_id = conn.execute(
        text("SELECT id FROM problems WHERE course_id = :c AND title = :t AND archived_at IS NULL"),
        {"c": course_id, "t": title},
    ).scalar_one()
    rows = conn.execute(
        text("SELECT id, input, expected, hidden, category FROM test_cases WHERE problem_id = :p ORDER BY id"),
        {"p": problem_id},
    )
    return [TestSpec(r.id, r.input, r.expected, r.hidden, r.category) for r in rows]


def main() -> int:
    course_id = int(sys.argv[1])
    lines = [
        f"Run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC on course {course_id}.",
        "",
        "| Problem | Expected category | Result | Failing categories | Caught as expected |",
        "| --- | --- | --- | --- | --- |",
    ]
    caught = 0
    with get_engine().connect() as conn:
        for title, code in SUBMISSIONS:
            g = grade(code, tests_for(conn, course_id, title))
            ok = g.status != "passed" and EXPECTED[title] in g.failed_categories
            caught += ok
            lines.append(
                f"| {title} | {EXPECTED[title]} | {g.status} | {', '.join(g.failed_categories) or '-'} | "
                f"{'yes' if ok else '**no**'} |"
            )
    lines += ["", f"{caught} of {len(SUBMISSIONS)} wrong solutions fail in the expected category."]
    print("\n".join(lines))
    return 0 if caught == len(SUBMISSIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
