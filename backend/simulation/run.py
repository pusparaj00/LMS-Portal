"""Compare adaptive and random item selection and two baselines on simulated students (TR-V-05, TR-M-06).

Usage (from backend/): python -m simulation.run [--students N] [--seed S] [--bank DIR] > result.md
"""
import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.diagnostic import pooled, selection
from app.mastery import core
from simulation import model

BKT_LEARN = 0.1  # BKT's transition probability: the one thing that distinguishes it from the update rule
ECE_BINS = 10
POLICIES = ("adaptive", "random", "bkt", "irt_only", "cat_info", "fixed")
SELECTORS = ("adaptive", "random", "cat_info", "fixed")  # ways of choosing questions, each also estimated pooled
HELD = ("adaptive", "random", "bkt", "irt_only")  # predictors scored on held-out responses
POOLED = tuple(f"{p}_pooled" for p in SELECTORS)  # the same questions, estimated with the pooled model


def most_informative(pool: list[selection.Item], ability: float) -> selection.Item:
    """The textbook adaptive test (TR-V-05): the question with the largest 2PL Fisher information a^2 P (1 - P) at the
    current one-number ability estimate, with no concept coverage term. Ties go to the lowest id."""
    def information(item: selection.Item) -> float:
        p = selection.prob_correct(ability, item.a, item.b)
        return item.a ** 2 * p * (1.0 - p)

    return max(sorted(pool, key=lambda i: i.id), key=information)


def predict_from_mastery(item: selection.Item, mastery: dict[int, float]) -> float:
    slip, guess = core.DEFAULT_PARAMS[selection.EVIDENCE_TYPE[item.kind]]
    weights = np.array(list(item.concepts.values()))
    weights = weights / weights.sum()
    p = np.array([mastery[c] * (1 - slip) + (1 - mastery[c]) * guess for c in item.concepts])
    return float(p @ weights)


def run_student(
    policy: str, items, outcomes: np.ndarray, truth: np.ndarray, rng, concepts: int, seed: str = "",
    prior: dict | None = None,
):
    """One placement test. Returns (error after each item, mastery, ability after each item, asked ids)."""
    mastery = {c: 0.5 for c in range(concepts)}
    asked: list[int] = []
    responses: list[tuple[float, float, bool, str]] = []
    given: list[selection.Response] = []
    errors = []
    abilities = []
    for _ in range(selection.max_questions(items)):
        if policy == "adaptive":
            item = selection.select_next(items, given, seed, **(prior or {}))
        elif policy == "cat_info":
            item = most_informative(selection.allowed(items, asked), selection.eap_theta(responses))
        elif policy == "fixed":
            item = min(selection.allowed(items, asked), key=lambda i: i.id)
        else:
            pool = selection.allowed(items, asked)
            item = pool[rng.integers(len(pool))]
        correct = bool(outcomes[item.id])
        asked.append(item.id)
        responses.append((item.a, item.b, correct, item.kind))
        given.append((item.id, correct, selection.EVIDENCE_TYPE[item.kind]))
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


def independent_mastery(items, outcomes: np.ndarray, asked: list[int], concepts: int) -> dict[int, float]:
    """The mastery rule's per-concept estimate after the asked questions (what the app did before the pooled model)."""
    mastery = {c: 0.5 for c in range(concepts)}
    for i in asked:
        slip, guess = core.DEFAULT_PARAMS[selection.EVIDENCE_TYPE[items[i].kind]]
        for c, w in items[i].concepts.items():
            mastery[c] = core.weighted_update(mastery[c], slip, guess, bool(outcomes[i]), min(1.0, w))
    return mastery


def pooled_answers(items, outcomes: np.ndarray, asked: list[int]) -> list[pooled.Answer]:
    out = []
    for i in asked:
        slip, guess = selection.slip_guess(selection.EVIDENCE_TYPE[items[i].kind], items[i].options)
        out.append(pooled.Answer(items[i].concepts, items[i].a, items[i].b, slip, guess, bool(outcomes[i])))
    return out


def pooled_trace(items, outcomes: np.ndarray, truth: np.ndarray, asked: list[int], concepts: int, **prior):
    """Pooled estimate after each question: error per prefix, and the estimate after 5 and after all questions."""
    errors, five = [], None
    answers = pooled_answers(items, outcomes, asked)
    for n in range(1, len(asked) + 1):
        theta, covariance = pooled.fit(answers[:n], concepts, **prior)
        estimate = pooled.mastery(theta, covariance)
        errors.append(float(np.mean(np.abs(estimate - truth))))
        if n == 5:
            five = estimate
    return errors, five, theta, covariance


def pooled_success(item, theta: np.ndarray, covariance: np.ndarray) -> float:
    """Chance of a right answer to a held-out question, with the spread of the ability estimate taken into account."""
    slip, guess = selection.slip_guess(selection.EVIDENCE_TYPE[item.kind], item.options)
    w = np.zeros(len(theta))
    for c, weight in item.concepts.items():
        w[c] = weight
    w = w / w.sum()
    spread = np.sqrt(1.0 + np.pi * (pooled.D * item.a) ** 2 * float(w @ covariance @ w) / 8.0)
    link = 1.0 / (1.0 + np.exp(-pooled.D * item.a * (float(w @ theta) - item.b) / spread))
    return guess + (1.0 - slip - guess) * float(link)



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
    """Error of the estimate against the error of predicting the population mean of the target (TR-V-06)."""
    return {
        "estimate_rmse": float(np.sqrt(np.mean((estimate - target) ** 2))),
        "population_mean_rmse": float(np.sqrt(np.mean((target - target.mean()) ** 2))),
    }


def simulate(students: int, seed: int, bank: model.Bank, prior: dict | None = None) -> dict:
    prior = prior or {}
    rng = np.random.default_rng(seed)
    items, k = bank.items, len(bank.concepts)
    theta = model.make_students(rng, students, k)
    mastery_true = model.true_mastery(theta)
    a_true, b_true = model.true_item_params(rng, items)
    probabilities = model.response_probabilities(theta, items, a_true, b_true)
    outcomes = (rng.random(probabilities.shape) < probabilities).astype(int)  # one fixed answer per student and item

    length = selection.max_questions(items)
    curves = {p: np.zeros((students, length)) for p in (*POLICIES, *POOLED)}
    held_scores = {p: [] for p in (*HELD, "adaptive_pooled", "random_pooled", "prior_only")}
    held_labels: list[int] = []
    coverage = {p: [] for p in POLICIES}
    correlation = {p: [] for p in (*POLICIES, *POOLED)}
    five = {name: ([], []) for name in ("independent_all", "independent_tested", "pooled_all", "pooled_tested")}
    for s in range(students):
        asked_by_policy = {}
        pooled_by_policy = {}
        for policy in POLICIES:
            run_rng = np.random.default_rng([seed, s])
            errors, mastery, abilities, asked = run_student(
                policy, items, outcomes[s], mastery_true[s], run_rng, k, f"{seed}:{s}", prior
            )
            curves[policy][s] = errors
            asked_by_policy[policy] = (mastery, abilities[-1], asked)
            coverage[policy].append(len({c for i in asked for c in items[i].concepts}))
            estimate = [mastery[c] for c in range(k)]
            correlation[policy].append(float(np.corrcoef(estimate, mastery_true[s])[0, 1]))
            if policy in SELECTORS:
                errors, after_five, theta_hat, covariance = pooled_trace(
                    items, outcomes[s], mastery_true[s], asked, k, **prior
                )
                curves[f"{policy}_pooled"][s] = errors
                pooled_by_policy[policy] = (theta_hat, covariance)
                estimate_pooled = pooled.mastery(theta_hat, covariance)
                correlation[f"{policy}_pooled"].append(float(np.corrcoef(estimate_pooled, mastery_true[s])[0, 1]))
            if policy == "adaptive":
                tested = sorted({c for i in asked[:5] for c in items[i].concepts})
                independent_5 = independent_mastery(items, outcomes[s], asked[:5], k)
                for name, values in (
                    ("independent", np.array([independent_5[c] for c in range(k)])), ("pooled", after_five),
                ):
                    five[f"{name}_all"][0].append(float(values.mean()))
                    five[f"{name}_all"][1].append(float(mastery_true[s].mean()))
                    five[f"{name}_tested"][0].append(float(values[tested].mean()))
                    five[f"{name}_tested"][1].append(float(mastery_true[s][tested].mean()))
        # held-out responses: bank items asked by neither test, so no predictor has seen them
        seen = set(asked_by_policy["adaptive"][2]) | set(asked_by_policy["random"][2])
        held = [i for i in items if i.id not in seen]
        held_labels += [int(outcomes[s][i.id]) for i in held]
        for policy in HELD:
            mastery, ability, _ = asked_by_policy[policy]
            if policy == "irt_only":
                held_scores[policy] += [
                    selection.observed_probability(ability, i.a, i.b, i.kind) for i in held
                ]
            else:
                held_scores[policy] += [predict_from_mastery(i, mastery) for i in held]
        held_scores["prior_only"] += [predict_from_mastery(i, {c: 0.5 for c in range(k)}) for i in held]
        for policy in ("adaptive", "random"):
            theta_hat, covariance = pooled_by_policy[policy]
            held_scores[f"{policy}_pooled"] += [pooled_success(i, theta_hat, covariance) for i in held]

    labels = np.array(held_labels)
    return {
        "curves": {p: curves[p].mean(axis=0) for p in (*POLICIES, *POOLED)},
        "auc": {p: auc(np.array(v), labels) for p, v in held_scores.items()},
        "ece": {p: calibration_error(np.array(v), labels) for p, v in held_scores.items()},
        "held_out_responses": len(labels),
        "coverage": {p: float(np.mean(v)) for p, v in coverage.items()},
        "correlation": {p: float(np.nanmean(v)) for p, v in correlation.items()},
        # TR-V-06: error of the average mastery after 5 questions against the true average mastery
        "sanity_5_items": {name: _rmse_pair(np.array(e), np.array(t)) for name, (e, t) in five.items()},
    }


def items_to_reach(curve: np.ndarray, threshold: float) -> int | None:
    reached = np.nonzero(curve <= threshold)[0]
    return int(reached[0]) + 1 if len(reached) else None


def report(result: dict, args: argparse.Namespace) -> str:
    curves = result["curves"]
    threshold = float(curves["random"][-1])
    adaptive_items = items_to_reach(curves["adaptive"], threshold)
    length = len(curves["random"])
    fewer = (length - adaptive_items) / length * 100 if adaptive_items else None
    pooled_threshold = float(curves["random_pooled"][-1])
    pooled_items = items_to_reach(curves["adaptive_pooled"], pooled_threshold)
    pooled_fewer = (length - pooled_items) / length * 100 if pooled_items else None
    lines = [
        "# Diagnostic simulation results",
        "",
        f"- Command: `python -m simulation.run --students {args.students} --seed {args.seed}"
        f"{args.prior_flags}`",
        f"- Run at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Simulated students: {args.students}, bank: {len(args.items)} items, test length: {length}",
        "",
        "## Error of the mastery vector (mean absolute error against true mastery)",
        "",
        "| Items asked | adaptive | random | BKT (random order) | adaptive + pooled | random + pooled |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for n in sorted({1, 3, 5, 8, 10, 16, length}):
        lines.append(
            f"| {n} | {curves['adaptive'][n - 1]:.3f} | {curves['random'][n - 1]:.3f} | {curves['bkt'][n - 1]:.3f} |"
            f" {curves['adaptive_pooled'][n - 1]:.3f} | {curves['random_pooled'][n - 1]:.3f} |"
        )
    lines += [
        "",
        f"Threshold = the error random selection reaches after {length} items ({threshold:.3f}). "
        + (
            f"Adaptive selection reaches it after {adaptive_items} items, {fewer:.0f}% fewer than random "
            f"(target in the PRD: at least 30% fewer)."
            if adaptive_items
            else "Adaptive selection does not reach it within the test length."
        ),
        "",
        f"With the pooled estimate the threshold is random's error after {length} items ({pooled_threshold:.3f}). "
        + (
            f"Adaptive selection reaches it after {pooled_items} items, {pooled_fewer:.0f}% fewer than random."
            if pooled_items
            else "Adaptive selection does not reach it within the test length."
        ),
        "",
        "## Selection baselines, all with the pooled estimate (TR-V-05)",
        "",
        "The same estimator for every way of choosing questions, so the comparison is about the choice alone. "
        "Max-information adaptive is the textbook adaptive test: the question with the largest 2PL information at the "
        "current ability estimate, with no concept coverage term. Fixed order asks the allowed questions in id order.",
        "",
        "| Items asked | adaptive | max-information adaptive | random | fixed order |",
        "| --- | --- | --- | --- | --- |",
        *[
            f"| {n} | " + " | ".join(f"{curves[key][n - 1]:.3f}" for key in (
                "adaptive_pooled", "cat_info_pooled", "random_pooled", "fixed_pooled")) + " |"
            for n in sorted({1, 3, 5, 8, 10, 16, length})
        ],
        "",
        f"Items needed to reach random selection's final pooled error ({pooled_threshold:.3f}), out of {length}: "
        + ", ".join(
            f"{name} {reach if (reach := items_to_reach(curves[key], pooled_threshold)) else 'not reached'}"
            for key, name in (("adaptive_pooled", "adaptive"), ("cat_info_pooled", "max-information adaptive"),
                              ("fixed_pooled", "fixed order"))
        ) + ".",
        "",
        "## Coverage and ranking after the whole test",
        "",
        "| Policy | Concepts touched (of 12) | Correlation of estimate with true mastery |",
        "| --- | --- | --- |",
        *[
            f"| {name} | {result['coverage'][key]:.1f} | {result['correlation'][key]:.3f} |"
            for key, name in (("adaptive", "adaptive"), ("random", "random"), ("bkt", "BKT (random order)"))
        ],
        *[
            f"| {name} | {result['coverage'][key]:.1f} | {result['correlation'][key + '_pooled']:.3f} |"
            for key, name in (("adaptive", "adaptive + pooled"), ("random", "random + pooled"),
                              ("cat_info", "max-information adaptive + pooled"), ("fixed", "fixed order + pooled"))
        ],
        "",
        "## Five-item sanity test (TR-V-06)",
        "",
        "RMSE of the average mastery estimated after 5 adaptive items against the student's true average mastery, "
        "compared with predicting the population mean of the true average mastery.",
        "",
        "| Estimate | True value is | Estimate RMSE | Population-mean RMSE | Result |",
        "| --- | --- | --- | --- | --- |",
        *[
            f"| {est} | {label} | {v['estimate_rmse']:.3f} | {v['population_mean_rmse']:.3f} | "
            f"{'beats the mean predictor' if v['estimate_rmse'] < v['population_mean_rmse'] else 'does NOT beat it'} |"
            for est, key_est in (("independent", "independent"), ("pooled", "pooled"))
            for label, v in (
                ("average over all concepts", result["sanity_5_items"][f"{key_est}_all"]),
                ("average over the concepts the 5 items tested", result["sanity_5_items"][f"{key_est}_tested"]),
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
        "adaptive_pooled": "Adaptive selection + pooled estimate",
        "random_pooled": "Random selection + pooled estimate",
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
    parser.add_argument("--correlation", type=float, default=pooled.CORRELATION)
    parser.add_argument("--prior-sd", type=float, default=pooled.PRIOR_SD)
    parser.add_argument("--cover-weight", type=float, default=selection.COVER_WEIGHT)
    parser.add_argument("--true-guess-from-options", action="store_true",
                        help="simulated students guess a tracing item right 1 / options of the time")
    parser.add_argument("--no-option-chance", action="store_true",
                        help="the app assumes one guess rate for every tracing item (the behaviour before step 68)")
    root = Path(__file__).resolve().parents[1]
    default_bank = next(p for p in (root / "data" / "bank", root.parent / "data" / "bank") if p.exists())
    parser.add_argument("--bank", type=Path, default=default_bank)
    args = parser.parse_args()
    model.TRUE_GUESS_FROM_OPTIONS = args.true_guess_from_options
    selection.USE_OPTION_CHANCE = not args.no_option_chance
    selection.COVER_WEIGHT = args.cover_weight
    bank = model.load_bank(args.bank)
    args.items = bank.items
    prior = {"correlation": args.correlation, "sd": args.prior_sd}
    args.prior_flags = (
        "" if (args.correlation, args.prior_sd) == (pooled.CORRELATION, pooled.PRIOR_SD)
        else f" --correlation {args.correlation} --prior-sd {args.prior_sd}"
    ) + (f" --cover-weight {args.cover_weight}" if args.cover_weight != parser.get_default("cover_weight") else "") + (
        " --true-guess-from-options" if args.true_guess_from_options else ""
    ) + (
        " --no-option-chance" if args.no_option_chance else ""
    )
    sys.stdout.write(report(simulate(args.students, args.seed, bank, prior), args))


if __name__ == "__main__":
    main()
