"""Non-circular diagnostic evaluation from MiroFish-generated synthetic students.

Reads synthetic_students.json (produced by MiroFish/student_eval/generate_students.py) and runs the
same adaptive-vs-random comparison as simulation.run, but with responses and true mastery taken from
LLM personas instead of the 2PL response model. This breaks the circularity called out in TR-V-05.

Usage (from backend/): python -m simulation.noncircular --students-json <path> [--bank DIR]
"""
import argparse
import json
from pathlib import Path

import numpy as np

from app.diagnostic import pooled, selection
from simulation import run

SHORT_CODING_MAX_B = 0.5  # must match the generator


def load_bank_items(bank_dir: Path, mcq_known: int) -> tuple[list[selection.Item], list[str], int, int]:
    """Items the persona file has answers for: its first `mcq_known` tracing items (later ones are newer)."""
    concepts = json.loads((bank_dir / "concepts.json").read_text(encoding="utf-8"))
    index = {c["name"]: i for i, c in enumerate(concepts)}
    mcq = json.loads((bank_dir / "items.json").read_text(encoding="utf-8"))[:mcq_known]
    code = []
    for path in sorted((bank_dir / "problems").glob("*.json")):
        code += json.loads(path.read_text(encoding="utf-8"))
    code = [p for p in code if float(p["difficulty_b"]) <= SHORT_CODING_MAX_B]

    items: list[selection.Item] = []
    for p in code:
        items.append(
            selection.Item(
                len(items), "code", p["discrimination_a"], p["difficulty_b"],
                {index[c["name"]]: c["weight"] for c in p["concepts"]},
            )
        )
    for m in mcq:
        items.append(
            selection.Item(
                len(items), "mcq", m["discrimination_a"], m["difficulty_b"],
                {index[c["name"]]: c["weight"] for c in m["concepts"]},
            )
        )
    return items, [c["name"] for c in concepts], len(code), len(mcq)


def build_matrices(data: dict, items: list[selection.Item], concepts: list[str], n_code: int):
    k = len(concepts)
    outcomes = np.zeros((len(data["students"]), len(items)), dtype=int)
    truth = np.zeros((len(data["students"]), k))
    for s, student in enumerate(data["students"]):
        answers = student["answers"]
        for item in items:
            key = f"code:{item.id}" if item.kind == "code" else f"mcq:{item.id - n_code}"
            outcomes[s, item.id] = int(bool(answers.get(key)))
        truth[s] = [float(student["mastery_true"].get(c, 0.5)) for c in concepts]
    return outcomes, truth


def simulate_noncircular(
    outcomes: np.ndarray, truth: np.ndarray, items: list[selection.Item], k: int, prior: dict | None = None
) -> dict:
    prior = prior or {}
    students = len(outcomes)
    curves = {p: np.zeros((students, selection.max_questions(items))) for p in (*run.POLICIES, *run.POOLED)}
    coverage = {p: [] for p in run.POLICIES}
    correlation = {p: [] for p in (*run.POLICIES, *run.POOLED)}
    held_scores = {p: [] for p in (*run.POLICIES, *run.POOLED, "prior_only")}
    held_labels: list[int] = []
    five = {name: ([], []) for name in ("independent_all", "independent_tested", "pooled_all", "pooled_tested")}

    for s in range(students):
        asked_by_policy = {}
        pooled_by_policy = {}
        for policy in run.POLICIES:
            run_rng = np.random.default_rng([s])
            errors, mastery, abilities, asked = run.run_student(
                policy, items, outcomes[s], truth[s], run_rng, k, f"noncircular:{s}", prior
            )
            curves[policy][s] = errors
            asked_by_policy[policy] = (mastery, abilities[-1], asked)
            coverage[policy].append(len({c for i in asked for c in items[i].concepts}))
            estimate = [mastery[c] for c in range(k)]
            correlation[policy].append(float(np.corrcoef(estimate, truth[s])[0, 1]))
            if policy in ("adaptive", "random"):
                errors, after_five, theta_hat, covariance = run.pooled_trace(
                    items, outcomes[s], truth[s], asked, k, **prior
                )
                curves[f"{policy}_pooled"][s] = errors
                pooled_by_policy[policy] = (theta_hat, covariance)
                correlation[f"{policy}_pooled"].append(
                    float(np.corrcoef(pooled.mastery(theta_hat, covariance), truth[s])[0, 1])
                )
            if policy == "adaptive":
                tested = sorted({c for i in asked[:5] for c in items[i].concepts})
                independent_5 = run.independent_mastery(items, outcomes[s], asked[:5], k)
                for name, values in (
                    ("independent", np.array([independent_5[c] for c in range(k)])), ("pooled", after_five),
                ):
                    five[f"{name}_all"][0].append(float(values.mean()))
                    five[f"{name}_all"][1].append(float(truth[s].mean()))
                    five[f"{name}_tested"][0].append(float(values[tested].mean()))
                    five[f"{name}_tested"][1].append(float(truth[s][tested].mean()))

        seen = set(asked_by_policy["adaptive"][2]) | set(asked_by_policy["random"][2])
        held = [i for i in items if i.id not in seen]
        held_labels += [int(outcomes[s][i.id]) for i in held]
        for policy in run.POLICIES:
            mastery, ability, _ = asked_by_policy[policy]
            if policy == "irt_only":
                held_scores[policy] += [selection.observed_probability(ability, i.a, i.b, i.kind) for i in held]
            else:
                held_scores[policy] += [run.predict_from_mastery(i, mastery) for i in held]
        held_scores["prior_only"] += [run.predict_from_mastery(i, {c: 0.5 for c in range(k)}) for i in held]
        for policy in ("adaptive", "random"):
            theta_hat, covariance = pooled_by_policy[policy]
            held_scores[f"{policy}_pooled"] += [run.pooled_success(i, theta_hat, covariance) for i in held]

    labels = np.array(held_labels)
    return {
        "curves": {p: curves[p].mean(axis=0) for p in (*run.POLICIES, *run.POOLED)},
        "auc": {p: run.auc(np.array(v), labels) for p, v in held_scores.items()},
        "ece": {p: run.calibration_error(np.array(v), labels) for p, v in held_scores.items()},
        "coverage": {p: float(np.mean(v)) for p, v in coverage.items()},
        "correlation": {p: float(np.nanmean(v)) for p, v in correlation.items()},
        "sanity_5_items": {name: run._rmse_pair(np.array(e), np.array(t)) for name, (e, t) in five.items()},
    }


def report(result: dict, n_students: int, n_items: int) -> str:
    curves = result["curves"]
    threshold = float(curves["random"][-1])
    adaptive_items = run.items_to_reach(curves["adaptive"], threshold)
    pooled_threshold = float(curves["random_pooled"][-1])
    pooled_items = run.items_to_reach(curves["adaptive_pooled"], pooled_threshold)
    length = len(curves["random"])
    fewer = (length - adaptive_items) / length * 100 if adaptive_items else None
    lines = [
        "# Non-circular diagnostic simulation (MiroFish synthetic students)",
        "",
        f"- Students: {n_students}, items: {n_items}, test length: {length}",
        "",
        "## Error of the mastery vector (MAE against the persona's stated mastery)",
        "",
        "| Items asked | adaptive | random | adaptive + pooled | random + pooled |",
        "| --- | --- | --- | --- | --- |",
    ]
    for n in sorted({1, 3, 5, 8, 10, 16, length}):
        lines.append(
            f"| {n} | {curves['adaptive'][n - 1]:.3f} | {curves['random'][n - 1]:.3f} |"
            f" {curves['adaptive_pooled'][n - 1]:.3f} | {curves['random_pooled'][n - 1]:.3f} |"
        )
    lines += [
        "",
        f"Threshold = random's error after {length} items ({threshold:.3f}). "
        + (
            f"Adaptive reaches it after {adaptive_items} items ({fewer:.0f}% fewer; target 30%)."
            if adaptive_items
            else "Adaptive does not reach it."
        ),
        f"With the pooled estimate: random's error after {length} items is {pooled_threshold:.3f}; "
        + (f"adaptive reaches it after {pooled_items} items." if pooled_items else "adaptive does not reach it."),
        "",
        "## Coverage and ranking after the whole test",
        "",
        "| Policy | Concepts touched | Correlation with true mastery |",
        "| --- | --- | --- |",
        f"| adaptive | {result['coverage']['adaptive']:.1f} | {result['correlation']['adaptive']:.3f} |",
        f"| random | {result['coverage']['random']:.1f} | {result['correlation']['random']:.3f} |",
        f"| adaptive + pooled | {result['coverage']['adaptive']:.1f} | "
        f"{result['correlation']['adaptive_pooled']:.3f} |",
        f"| random + pooled | {result['coverage']['random']:.1f} | {result['correlation']['random_pooled']:.3f} |",
        "",
        "## Five-item sanity test (TR-V-06)",
        "",
        "Average mastery estimated after 5 adaptive questions against the persona's true average mastery, compared "
        "with predicting the population mean of it.",
        "",
        "| Estimate | True value is | Estimate RMSE | Population-mean RMSE | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for est in ("independent", "pooled"):
        for label, key in (("average over all concepts", "all"), ("average over tested concepts", "tested")):
            v = result["sanity_5_items"][f"{est}_{key}"]
            ok = v["estimate_rmse"] < v["population_mean_rmse"]
            lines.append(f"| {est} | {label} | {v['estimate_rmse']:.3f} | {v['population_mean_rmse']:.3f} | "
                         f"{'beats the mean' if ok else 'does NOT beat it'} |")
    lines += [
        "",
        "## Prediction of held-out responses",
        "",
        "| Predictor | AUC | ECE |",
        "| --- | --- | --- |",
        f"| Adaptive + mastery update | {result['auc']['adaptive']:.3f} | {result['ece']['adaptive']:.3f} |",
        f"| Random + mastery update | {result['auc']['random']:.3f} | {result['ece']['random']:.3f} |",
        f"| Adaptive + pooled estimate | {result['auc']['adaptive_pooled']:.3f} | "
        f"{result['ece']['adaptive_pooled']:.3f} |",
        f"| Random + pooled estimate | {result['auc']['random_pooled']:.3f} | {result['ece']['random_pooled']:.3f} |",
        f"| Ability-only 2PL baseline | {result['auc']['irt_only']:.3f} | {result['ece']['irt_only']:.3f} |",
        "",
        "These students are LLM personas, not real learners; the numbers are synthetic and labelled as such.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students-json", type=Path, required=True)
    parser.add_argument("--part", choices=("all", "first", "second"), default="all", help="a half of the students")
    parser.add_argument("--correlation", type=float, default=pooled.CORRELATION)
    parser.add_argument("--prior-sd", type=float, default=pooled.PRIOR_SD)
    root = Path(__file__).resolve().parents[1]
    default_bank = next(p for p in (root / "data" / "bank", root.parent / "data" / "bank") if p.exists())
    parser.add_argument("--bank", type=Path, default=default_bank)
    args = parser.parse_args()

    data = json.loads(args.students_json.read_text(encoding="utf-8"))
    answered = {int(k.split(":")[1]) for st in data["students"] for k in st["answers"] if k.startswith("mcq:")}
    items, concepts, n_code, _ = load_bank_items(args.bank, len(answered))
    outcomes, truth = build_matrices(data, items, concepts, n_code)
    half = len(outcomes) // 2
    chosen = {"all": slice(None), "first": slice(0, half), "second": slice(half, None)}[args.part]
    outcomes, truth = outcomes[chosen], truth[chosen]
    prior = {"correlation": args.correlation, "sd": args.prior_sd}
    print(report(simulate_noncircular(outcomes, truth, items, len(concepts), prior), len(outcomes), len(items)))


if __name__ == "__main__":
    main()
