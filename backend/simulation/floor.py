"""How low can the error of the mastery vector go with a given number of answers? (TR-V-05)

The oracle knows the simulator's true model (true item parameters, slip, guess, ability correlation) and uses the exact
Bayesian estimate (a Gaussian approximation), so no estimator on these students can do better on average than it does.
That separates "the estimator is poor" from "the answers do not contain enough information".

Usage (from backend/): python -m simulation.floor [--students N] [--seed S] > result.md
"""
import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.diagnostic import pooled
from simulation import model, run


def draw(seed: int, students: int, bank: model.Bank):
    """The same students, true item parameters and fixed answers as simulation.run.simulate."""
    rng = np.random.default_rng(seed)
    theta = model.make_students(rng, students, len(bank.concepts))
    truth = model.true_mastery(theta)
    a_true, b_true = model.true_item_params(rng, bank.items)
    probabilities = model.response_probabilities(theta, bank.items, a_true, b_true)
    outcomes = (rng.random(probabilities.shape) < probabilities).astype(int)
    return truth, a_true, b_true, outcomes


def oracle_mae(bank, truth, a_true, b_true, outcomes, chosen: list[list[int]]) -> float:
    """Mean absolute error of the oracle estimate when student s answered the items chosen[s]."""
    k = len(bank.concepts)
    correlation = model.ABILITY_CORRELATION**2
    errors = []
    for s, ids in enumerate(chosen):
        answers = [
            pooled.Answer(
                bank.items[i].concepts, a_true[i], b_true[i], model.TRUE_SLIP,
                model.TRUE_GUESS[bank.items[i].kind], bool(outcomes[s, i]),
            )
            for i in ids
        ]
        theta, covariance = pooled.fit(answers, k, 0.0, correlation, 1.0)
        estimate = pooled.mastery(theta, covariance, slope=model.MASTERY_SCALE)
        errors.append(float(np.mean(np.abs(estimate - truth[s]))))
    return float(np.mean(errors))


def best_per_concept(bank, a_true, b_true, per_concept: int) -> list[int]:
    """The most informative questions for each concept, the same for every student (not adaptive)."""
    chosen = []
    for c in range(len(bank.concepts)):
        own = [i for i, item in enumerate(bank.items) if max(item.concepts, key=item.concepts.get) == c]
        own.sort(key=lambda i: -a_true[i] / (1.0 + abs(b_true[i])))
        chosen += own[:per_concept]
    return chosen


def simulate(students: int, seed: int, bank: model.Bank) -> dict:
    truth, a_true, b_true, outcomes = draw(seed, students, bank)
    k = len(bank.concepts)
    rows = {}
    nobody = [[] for _ in range(students)]
    rows["no answers (the prior only)"] = (0, oracle_mae(bank, truth, a_true, b_true, outcomes, nobody))
    for per in (1, 2, 3):
        ids = best_per_concept(bank, a_true, b_true, per)
        rows[f"{per} best question per concept, same for everyone"] = (
            len(ids), oracle_mae(bank, truth, a_true, b_true, outcomes, [ids] * students)
        )
    asked, independent = [], []
    for s in range(students):
        _, mastery, _, order = run.run_student(
            "adaptive", bank.items, outcomes[s], truth[s], np.random.default_rng([seed, s]), k, f"{seed}:{s}"
        )
        asked.append(order)
        independent.append(float(np.mean([abs(mastery[c] - truth[s][c]) for c in range(k)])))
    length = len(asked[0])
    rows[f"the {length} questions the adaptive test chose"] = (
        length, oracle_mae(bank, truth, a_true, b_true, outcomes, asked)
    )
    everything = list(range(len(bank.items)))
    rows[f"the whole bank, {len(everything)} questions"] = (
        len(everything), oracle_mae(bank, truth, a_true, b_true, outcomes, [everything] * students)
    )
    return {"rows": rows, "independent": float(np.mean(independent)), "length": length}


def report(result: dict, args: argparse.Namespace, bank: model.Bank) -> str:
    lines = [
        "# Error floor of the mastery vector (TR-V-05)",
        "",
        f"- Command: `python -m simulation.floor --students {args.students} --seed {args.seed}`",
        f"- Run at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Simulated students: {args.students}, bank: {len(bank.items)} questions, {len(bank.concepts)} concepts",
        "",
        "The oracle knows the simulator's true item parameters, slip, guess and ability correlation, and uses the "
        "exact Bayesian estimate (a Gaussian approximation). No estimator can beat it on average on these students.",
        "",
        "| Answers behind the estimate | Questions | Oracle error (mean absolute) |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {name} | {n} | {mae:.3f} |" for name, (n, mae) in result["rows"].items()]
    lines += [
        "",
        f"For reference, the app's independent per-concept estimate after the same {result['length']} adaptive "
        f"questions has error {result['independent']:.3f}. The PRD target is an error under 0.15.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=300)
    parser.add_argument("--seed", type=int, default=2026)
    root = Path(__file__).resolve().parents[1]
    default_bank = next(p for p in (root / "data" / "bank", root.parent / "data" / "bank") if p.exists())
    parser.add_argument("--bank", type=Path, default=default_bank)
    args = parser.parse_args()
    bank = model.load_bank(args.bank)
    sys.stdout.write(report(simulate(args.students, args.seed, bank), args, bank))


if __name__ == "__main__":
    main()
