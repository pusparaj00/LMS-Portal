"""F-29, TR-M-17: does the next problem fit the student's level? Old rule (easiest unsolved) against the new one.

Run inside the api container:  python -m evaluation.recommend_fit [--seed S] [--trials N]

For each concept of the course, each mastery level from 0.1 to 0.9, and N random sets of already-solved problems, both rules
pick a problem from the real bank. The fit is judged with the placement test's own model: the chance of success is
sigmoid(logit(mastery) - difficulty). That is a model-internal measure, not learning: no student is involved. The good band
(0.5 to 0.85) is a design choice, stated here so it can be argued with.
"""
import argparse
import math
import random
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import get_engine

BAND = (0.5, 0.85)
TARGET = 0.7  # the chance of success the new rule aims for
LEVELS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def success(p: float, b: float) -> float:
    return 1 / (1 + math.exp(-(logit(p) - b)))


def easiest(unsolved: list[tuple[int, float]], p: float) -> tuple[int, float]:
    return min(unsolved, key=lambda x: (x[1], x[0]))


def goal(p: float) -> float:
    return logit(p) - logit(TARGET)


def closest(unsolved: list[tuple[int, float]], p: float) -> tuple[int, float]:
    return min(unsolved, key=lambda x: (abs(x[1] - goal(p)), x[0]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--trials", type=int, default=200)
    args = parser.parse_args()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.name, p.id, p.difficulty_b FROM problems p JOIN problem_concepts pc ON pc.problem_id = p.id"
                " JOIN concepts c ON c.id = pc.concept_id WHERE p.kind = 'code' AND p.archived_at IS NULL"
            )
        ).all()
    bank: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for name, pid, b in rows:
        bank[name].append((pid, float(b)))
    rng = random.Random(args.seed)
    print(f"# Recommendation fit\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}; seed {args.seed}; {args.trials} trials per "
          f"concept and level; {len(bank)} concepts, {len(rows)} code problems.\n")
    print("| Rule | Picks in the 0.5-0.85 success band | Mean gap from the difficulty that gives a 0.7 chance | Picks with success above 0.95 |")
    print("| --- | --- | --- | --- |")
    for label, rule in (("easiest unsolved (before)", easiest), ("closest to a 0.7 chance (after)", closest)):
        rng = random.Random(args.seed)
        total = in_band = too_easy = 0
        gap = 0.0
        for problems in bank.values():
            for p in LEVELS:
                for _ in range(args.trials):
                    solved = rng.randint(0, len(problems) - 1)
                    unsolved = rng.sample(problems, len(problems) - solved)
                    pid, b = rule(unsolved, p)
                    s = success(p, b)
                    total += 1
                    in_band += BAND[0] <= s <= BAND[1]
                    too_easy += s > 0.95
                    gap += abs(b - goal(p))
        print(f"| {label} | {in_band / total:.0%} | {gap / total:.2f} | {too_easy / total:.0%} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
