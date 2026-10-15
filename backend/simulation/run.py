"""Compare adaptive and random item selection and two baselines on simulated students (TR-V-05, TR-M-06).

Usage (from backend/): python -m simulation.run [--students N] [--seed S] [--bank DIR] > result.md
"""
import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.diagnostic import selection
from app.mastery import core
from simulation import model

BKT_LEARN = 0.1  # BKT's transition probability: the one thing that distinguishes it from the update rule
ECE_BINS = 10
POLICIES = ("adaptive", "random", "bkt", "irt_only")


def predict_from_mastery(item: selection.Item, mastery: dict[int, float]) -> float:
    slip, guess = core.DEFAULT_PARAMS[selection.EVIDENCE_TYPE[item.kind]]
    weights = np.array(list(item.concepts.values()))
    weights = weights / weights.sum()
    p = np.array([mastery[c] * (1 - slip) + (1 - mastery[c]) * guess for c in item.concepts])
    return float(p @ weights)


def run_student(policy: str, items, outcomes: np.ndarray, truth: np.ndarray, rng, concepts: int):
    """One placement test. Returns (error after each item, mastery, ability after each item, asked ids)."""
    mastery = {c: 0.5 for c in range(concepts)}
    asked: list[int] = []
    responses: list[tuple[float, float, bool, str]] = []
    errors = []
    abilities = []
    for _ in range(selection.MAX_ITEMS):
        theta = selection.eap_theta(responses)
        if policy == "adaptive":
            item = selection.select_next(items, set(asked), mastery, theta)
        else:
            pool = selection.eligible(items, set(asked))
            item = pool[rng.integers(len(pool))]
        correct = bool(outcomes[item.id])
        asked.append(item.id)
        responses.append((item.a, item.b, correct, item.kind))
        slip, guess = core.DEFAULT_PARAMS[selection.EVIDENCE_TYPE[item.kind]]
        for c, w in item.concepts.items():
            if policy == "bkt":
                posterior = core.bayes_update(mastery[c], 0.1, 0.2, correct)
                mastery[c] = posterior + (1 - posterior) * BKT_LEARN
            else:
                mastery[c] = core.weighted_update(mastery[c], slip, guess, correct, min(1.0, w))
        errors.append(float(np.mean([abs(mastery[c] - truth[c]) for c in range(concepts)])))
        abilities.append(selection.eap_theta(responses))
    return errors, mastery, abilities, asked


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Probability a random correct response is scored above a random incorrect one (ties count half)."""
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores))
    start = 0
    while start < len(scores):
        end = start
        while end + 1 < len(scores) and sorted_scores[end + 1] == sorted_scores[start]:
            end += 1
        ranks[order[start : end + 1]] = (start + end) / 2 + 1
        start = end + 1
    positives = labels.sum()
    negatives = len(labels) - positives
    return float((ranks[labels == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def calibration_error(scores: np.ndarray, labels: np.ndarray) -> float:
    bins = np.minimum((scores * ECE_BINS).astype(int), ECE_BINS - 1)
    total = 0.0
    for b in range(ECE_BINS):
        mask = bins == b
        if mask.any():
            total += mask.mean() * abs(scores[mask].mean() - labels[mask].mean())
    return float(total)


def _rmse_pair(estimate: np.ndarray, target: np.ndarray) -> dict[str, float]:
    return {
        "estimate_rmse": float(np.sqrt(np.mean((estimate - target) ** 2))),
        "population_mean_rmse": float(np.sqrt(np.mean(target**2))),
    }


def simulate(students: int, seed: int, bank: model.Bank) -> dict:
    rng = np.random.default_rng(seed)
    items, k = bank.items, len(bank.concepts)
    theta = model.make_students(rng, students, k)
    mastery_true = model.true_mastery(theta)
    a_true, b_true = model.true_item_params(rng, items)
    probabilities = model.response_probabilities(theta, items, a_true, b_true)
    outcomes = (rng.random(probabilities.shape) < probabilities).astype(int)  # one fixed answer per student and item

    curves = {p: np.zeros((students, selection.MAX_ITEMS)) for p in POLICIES}
    held_scores = {p: [] for p in (*POLICIES, "prior_only")}
    held_labels: list[int] = []
    coverage = {p: [] for p in POLICIES}
    correlation = {p: [] for p in POLICIES}
    ability_after_5: list[float] = []
    tested_ability_5: list[float] = []
    for s in range(students):
        asked_by_policy = {}
        for policy in POLICIES:
            run_rng = np.random.default_rng([seed, s])
            errors, mastery, abilities, asked = run_student(
                policy, items, outcomes[s], mastery_true[s], run_rng, k
            )
            curves[policy][s] = errors
            asked_by_policy[policy] = (mastery, abilities[-1], asked)
            coverage[policy].append(len({c for i in asked for c in items[i].concepts}))
            estimate = [mastery[c] for c in range(k)]
            correlation[policy].append(float(np.corrcoef(estimate, mastery_true[s])[0, 1]))
            if policy == "adaptive":
                ability_after_5.append(abilities[4])
                first_five = [items[i] for i in asked[:5]]
                tested_ability_5.append(
                    float(np.mean([np.mean([theta[s][c] for c in it.concepts]) for it in first_five]))
                )
        # held-out responses: bank items asked by neither test, so no predictor has seen them
        seen = set(asked_by_policy["adaptive"][2]) | set(asked_by_policy["random"][2])
        held = [i for i in items if i.id not in seen]
        held_labels += [int(outcomes[s][i.id]) for i in held]
        for policy in POLICIES:
            mastery, ability, _ = asked_by_policy[policy]
            if policy == "irt_only":
                held_scores[policy] += [
                    selection.observed_probability(ability, i.a, i.b, i.kind) for i in held
                ]
            else:
                held_scores[policy] += [predict_from_mastery(i, mastery) for i in held]
        held_scores["prior_only"] += [predict_from_mastery(i, {c: 0.5 for c in range(k)}) for i in held]

    labels = np.array(held_labels)
    return {
        "curves": {p: curves[p].mean(axis=0) for p in POLICIES},
        "auc": {p: auc(np.array(v), labels) for p, v in held_scores.items()},
        "ece": {p: calibration_error(np.array(v), labels) for p, v in held_scores.items()},
        "held_out_responses": len(labels),
        "coverage": {p: float(np.mean(v)) for p, v in coverage.items()},
        "correlation": {p: float(np.nanmean(v)) for p, v in correlation.items()},
        # TR-V-06: error of the 5-item ability estimate against the student's true average ability
        "sanity_5_items": {
            "all_concepts": _rmse_pair(np.array(ability_after_5), theta.mean(axis=1)),
            "tested_concepts": _rmse_pair(np.array(ability_after_5), np.array(tested_ability_5)),
        },
    }


def items_to_reach(curve: np.ndarray, threshold: float) -> int | None:
    reached = np.nonzero(curve <= threshold)[0]
    return int(reached[0]) + 1 if len(reached) else None


def report(result: dict, args: argparse.Namespace) -> str:
    curves = result["curves"]
    threshold = float(curves["random"][-1])
    adaptive_items = items_to_reach(curves["adaptive"], threshold)
    fewer = (selection.MAX_ITEMS - adaptive_items) / selection.MAX_ITEMS * 100 if adaptive_items else None
    lines = [
        "# Diagnostic simulation results",
        "",
        f"- Command: `python -m simulation.run --students {args.students} --seed {args.seed}`",
        f"- Run at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Simulated students: {args.students}, bank: {len(args.items)} items, test length: {selection.MAX_ITEMS}",
        "",
        "## Error of the mastery vector (mean absolute error against true mastery)",
        "",
        "| Items asked | adaptive | random | BKT (random order) |",
        "| --- | --- | --- | --- |",
    ]
    for n in (1, 3, 5, 8, 10):
        lines.append(
            f"| {n} | {curves['adaptive'][n - 1]:.3f} | {curves['random'][n - 1]:.3f} | {curves['bkt'][n - 1]:.3f} |"
        )
    lines += [
        "",
        f"Threshold = the error random selection reaches after {selection.MAX_ITEMS} items ({threshold:.3f}). "
        + (
            f"Adaptive selection reaches it after {adaptive_items} items, {fewer:.0f}% fewer than random "
            f"(target in the PRD: at least 30% fewer)."
            if adaptive_items
            else "Adaptive selection does not reach it within the test length."
        ),
        "",
        "## Coverage and ranking after 10 items",
        "",
        "| Policy | Concepts touched (of 12) | Correlation of estimate with true mastery |",
        "| --- | --- | --- |",
        *[
            f"| {name} | {result['coverage'][key]:.1f} | {result['correlation'][key]:.3f} |"
            for key, name in (("adaptive", "adaptive"), ("random", "random"), ("bkt", "BKT (random order)"))
        ],
        "",
        "## Five-item sanity test (TR-V-06)",
        "",
        "RMSE of the ability estimate after 5 adaptive items, against two definitions of true ability, "
        "compared with predicting the population mean (ability 0).",
        "",
        "| True ability is | Estimate RMSE | Population-mean RMSE | Result |",
        "| --- | --- | --- | --- |",
        *[
            f"| {label} | {v['estimate_rmse']:.3f} | {v['population_mean_rmse']:.3f} | "
            f"{'beats the mean predictor' if v['estimate_rmse'] < v['population_mean_rmse'] else 'does NOT beat it'} |"
            for label, v in (
                (
                    "the average over all 12 concepts (declared before the first run)",
                    result["sanity_5_items"]["all_concepts"],
                ),
                ("the average over the concepts the 5 items tested", result["sanity_5_items"]["tested_concepts"]),
            )
        ],
        "",
        "## Prediction of held-out responses",
        "",
        f"{result['held_out_responses']} responses to bank items the adaptive test did not ask, pooled over students.",
        "",
        "| Predictor | AUC | Calibration error (ECE, 10 bins) |",
        "| --- | --- | --- |",
    ]
    names = {
        "adaptive": "Adaptive selection + mastery update",
        "random": "Random selection + mastery update",
        "bkt": "BKT baseline (random order, learning rate 0.1)",
        "irt_only": "Ability-only 2PL baseline (random order)",
        "prior_only": "No evidence (every concept at its prior)",
    }
    for key, name in names.items():
        lines.append(f"| {name} | {result['auc'][key]:.3f} | {result['ece'][key]:.3f} |")
    lines += [
        "",
        "## Limits",
        "",
        "The students are synthetic and drawn from a different response model than the one the selector assumes "
        "(correlated continuous abilities, perturbed item parameters, different slip and guess values), but the "
        "simulator is my own and is not fitted to real learners. These numbers describe this bank and this "
        "simulator only, say nothing yet about real students, and the simulator was not changed after seeing results.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2026)
    root = Path(__file__).resolve().parents[1]
    default_bank = next(p for p in (root / "data" / "bank", root.parent / "data" / "bank") if p.exists())
    parser.add_argument("--bank", type=Path, default=default_bank)
    args = parser.parse_args()
    bank = model.load_bank(args.bank)
    args.items = bank.items
    sys.stdout.write(report(simulate(args.students, args.seed, bank), args))


if __name__ == "__main__":
    main()
