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

from app.diagnostic import selection
from simulation import run

SHORT_CODING_MAX_B = 0.5  # must match the generator


def load_bank_items(bank_dir: Path) -> tuple[list[selection.Item], list[str], int, int]:
    concepts = json.loads((bank_dir / "concepts.json").read_text(encoding="utf-8"))
    index = {c["name"]: i for i, c in enumerate(concepts)}
    mcq = json.loads((bank_dir / "items.json").read_text(encoding="utf-8"))
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


def simulate_noncircular(outcomes: np.ndarray, truth: np.ndarray, items: list[selection.Item], k: int) -> dict:
    students = len(outcomes)
    curves = {p: np.zeros((students, selection.max_questions(items))) for p in run.POLICIES}
    coverage = {p: [] for p in run.POLICIES}
    correlation = {p: [] for p in run.POLICIES}
    held_scores = {p: [] for p in (*run.POLICIES, "prior_only")}
    held_labels: list[int] = []
    ability_after_5: list[float] = []
    tested_ability_5: list[float] = []

    for s in range(students):
        asked_by_policy = {}
        for policy in run.POLICIES:
            run_rng = np.random.default_rng([s])
            errors, mastery, abilities, asked = run.run_student(
                policy, items, outcomes[s], truth[s], run_rng, k, f"noncircular:{s}"
            )
            curves[policy][s] = errors
            asked_by_policy[policy] = (mastery, abilities[-1], asked)
            coverage[policy].append(len({c for i in asked for c in items[i].concepts}))
            estimate = [mastery[c] for c in range(k)]
            correlation[policy].append(float(np.corrcoef(estimate, truth[s])[0, 1]))
            if policy == "adaptive":
                ability_after_5.append(abilities[4])
                first_five = [items[i] for i in asked[:5]]
                tested_ability_5.append(
                    float(np.mean([np.mean([truth[s][c] for c in it.concepts]) for it in first_five]))
                )

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

    labels = np.array(held_labels)
    return {
        "curves": {p: curves[p].mean(axis=0) for p in run.POLICIES},
        "auc": {p: run.auc(np.array(v), labels) for p, v in held_scores.items()},
        "ece": {p: run.calibration_error(np.array(v), labels) for p, v in held_scores.items()},
        "coverage": {p: float(np.mean(v)) for p, v in coverage.items()},
        "correlation": {p: float(np.nanmean(v)) for p, v in correlation.items()},
        "sanity_5_items": {
            "all_concepts": run._rmse_pair(np.array(ability_after_5), truth.mean(axis=1)),
            "tested_concepts": run._rmse_pair(np.array(ability_after_5), np.array(tested_ability_5)),
        },
    }


def report(result: dict, n_students: int, n_items: int) -> str:
    curves = result["curves"]
    threshold = float(curves["random"][-1])
    adaptive_items = run.items_to_reach(curves["adaptive"], threshold)
    length = len(curves["random"])
    fewer = (length - adaptive_items) / length * 100 if adaptive_items else None
    lines = [
        "# Non-circular diagnostic simulation (MiroFish synthetic students)",
        "",
        f"- Students: {n_students}, items: {n_items}, test length: {length}",
        "",
        "## Error of the mastery vector (MAE against the persona's stated mastery)",
        "",
        "| Items asked | adaptive | random |",
        "| --- | --- | --- |",
    ]
    for n in sorted({1, 3, 5, 8, 10, 16, length}):
        lines.append(f"| {n} | {curves['adaptive'][n - 1]:.3f} | {curves['random'][n - 1]:.3f} |")
    lines += [
        "",
        f"Threshold = random's error after {length} items ({threshold:.3f}). "
        + (
            f"Adaptive reaches it after {adaptive_items} items ({fewer:.0f}% fewer; target 30%)."
            if adaptive_items
            else "Adaptive does not reach it."
        ),
        "",
        "## Coverage and ranking after the whole test",
        "",
        "| Policy | Concepts touched | Correlation with true mastery |",
        "| --- | --- | --- |",
        f"| adaptive | {result['coverage']['adaptive']:.1f} | {result['correlation']['adaptive']:.3f} |",
        f"| random | {result['coverage']['random']:.1f} | {result['correlation']['random']:.3f} |",
        "",
        "## Five-item sanity test (TR-V-06)",
        "",
        "| True ability is | Estimate RMSE | Population-mean RMSE | Result |",
        "| --- | --- | --- | --- |",
    ]
    for label, key in (
        ("average over all concepts", "all_concepts"),
        ("average over tested concepts", "tested_concepts"),
    ):
        v = result["sanity_5_items"][key]
        ok = v["estimate_rmse"] < v["population_mean_rmse"]
        lines.append(f"| {label} | {v['estimate_rmse']:.3f} | {v['population_mean_rmse']:.3f} | "
                     f"{'beats the mean' if ok else 'does NOT beat it'} |")
    lines += [
        "",
        "## Prediction of held-out responses",
        "",
        "| Predictor | AUC | ECE |",
        "| --- | --- | --- |",
        f"| Adaptive + mastery update | {result['auc']['adaptive']:.3f} | {result['ece']['adaptive']:.3f} |",
        f"| Random + mastery update | {result['auc']['random']:.3f} | {result['ece']['random']:.3f} |",
        f"| Ability-only 2PL baseline | {result['auc']['irt_only']:.3f} | {result['ece']['irt_only']:.3f} |",
        "",
        "These students are LLM personas, not real learners; the numbers are synthetic and labelled as such.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students-json", type=Path, required=True)
    root = Path(__file__).resolve().parents[1]
    default_bank = next(p for p in (root / "data" / "bank", root.parent / "data" / "bank") if p.exists())
    parser.add_argument("--bank", type=Path, default=default_bank)
    args = parser.parse_args()

    data = json.loads(args.students_json.read_text(encoding="utf-8"))
    items, concepts, n_code, _ = load_bank_items(args.bank)
    outcomes, truth = build_matrices(data, items, concepts, n_code)
    result = simulate_noncircular(outcomes, truth, items, len(concepts))
    print(report(result, len(data["students"]), len(items)))


if __name__ == "__main__":
    main()
