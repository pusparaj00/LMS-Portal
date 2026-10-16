"""How well F-23's difficulty estimate imitates the bank's own difficulties (leave-one-out).

Usage (from backend/): python -m evaluation.difficulty_model
Each bank problem is held out in turn: the model, and the concept averages it uses, are fitted on the others only.
Baselines: always the bank mean, and the concept average alone. The bank's difficulties are its authors' judgement,
not calibrated on real answers, so this measures agreement with that judgement, not true difficulty.
"""
import numpy as np

from app import difficulty


def leave_one_out(problems: list[dict], ridge: float) -> dict[str, float]:
    errors = {"model": [], "bank mean": [], "concept average": []}
    for i, held in enumerate(problems):
        rest = problems[:i] + problems[i + 1:]
        fitted = difficulty.fit(rest, ridge)
        errors["model"].append(abs(fitted.estimate(held["statement"], held["reference"], held["concepts"]) - held["b"]))
        errors["bank mean"].append(abs(np.mean([p["b"] for p in rest]) - held["b"]))
        errors["concept average"].append(abs(difficulty.concept_prior(held["concepts"], rest) - held["b"]))
    return {name: float(np.mean(e)) for name, e in errors.items()}


def main() -> None:
    problems = difficulty.bank_problems()
    values = [p["b"] for p in problems]
    print(f"{len(problems)} coding problems; difficulty from {min(values)} to {max(values)}")
    print()
    print("| Ridge | Model MAE | Bank mean MAE | Concept average MAE |")
    print("| --- | --- | --- | --- |")
    for ridge in (0.1, 1.0, 3.0, 10.0, 30.0):
        r = leave_one_out(problems, ridge)
        print(f"| {ridge} | {r['model']:.3f} | {r['bank mean']:.3f} | {r['concept average']:.3f} |")
    print(f"\nridge in use: {difficulty.RIDGE}")


if __name__ == "__main__":
    main()
