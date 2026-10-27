"""Which of the AUC gaps between models are real? (TR-M-01, research only)

Every model predicts the same test answers in each fold (students are split into folds, so no test student is seen while
fitting). The pooled test predictions are then resampled by STUDENT, with replacement, 'bootstraps' times; each resample
gives an AUC per model and the differences between chosen pairs. Reported: the AUC of each model with a 95% percentile
interval, and for each pair the mean difference, its 95% interval and the share of resamples in which the first model
is ahead. An interval that contains 0 means the data cannot separate the two models.

    python significance.py assist09 [--folds 5] [--bootstraps 500] [--bkt] [--fit-skill]
    python significance.py ednet [--students 1500] [--folds 5] [--bootstraps 500] [--bkt] [--fit-skill]
"""
import argparse

import numpy as np
from calibration import fit_maps
from compare import (
    fit_params,
    load_assist09,
    load_ednet,
    predict_lms,
    predict_per_skill,
    predict_pybkt,
)
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

PAIRS = [
    ("lms_default", "skill_mean"), ("lms_platt", "lms_default"), ("lms_fitted_skill", "lms_default"),
    ("pybkt", "lms_default"), ("pybkt", "lms_fitted_skill"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["assist09", "ednet"])
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--students", type=int, default=1500)
    parser.add_argument("--bootstraps", type=int, default=500)
    parser.add_argument("--bkt", action="store_true")
    parser.add_argument("--fit-skill", action="store_true")
    args = parser.parse_args()
    data = load_assist09() if args.dataset == "assist09" else load_ednet(args.students)
    print(f"{args.dataset}: {len(data)} answers, {data.user_id.nunique()} students, "
          f"{data.skill_name.nunique()} skills\n", flush=True)
    truths, users = [], []
    predictions: dict[str, list[np.ndarray]] = {}
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=args.folds).split(data, groups=data["user_id"]), 1):
        train, test = data.iloc[tr].reset_index(drop=True), data.iloc[te].reset_index(drop=True)
        base = float(train["correct"].mean())
        truths.append(test["correct"].to_numpy().astype(float))
        users.append(test["user_id"].to_numpy())
        default = predict_lms(test)
        platt, _ = fit_maps(predict_lms(train), train["correct"].to_numpy().astype(float))
        by_skill = train.groupby("skill_name")["correct"].mean()
        found = {"skill_mean": test["skill_name"].map(by_skill).fillna(base).to_numpy(), "lms_default": default,
                 "lms_platt": platt(default)}
        if args.fit_skill:
            found["lms_fitted_skill"] = predict_per_skill(train, test, fit_params(train, with_learning=True))
        if args.bkt:
            found["pybkt"] = predict_pybkt(train, test, base)[0]
        for name, values in found.items():
            predictions.setdefault(name, []).append(values)
        print(f"fold {fold} done", flush=True)

    truth = np.concatenate(truths)
    who = np.concatenate(users)
    pooled = {name: np.concatenate(parts) for name, parts in predictions.items()}
    members = {user: np.flatnonzero(who == user) for user in np.unique(who)}
    user_list = list(members)
    rng = np.random.default_rng(0)
    point = {name: roc_auc_score(truth, values) for name, values in pooled.items()}
    boot = {name: [] for name in pooled}
    for _ in range(args.bootstraps):
        chosen = rng.integers(0, len(user_list), len(user_list))
        index = np.concatenate([members[user_list[i]] for i in chosen])
        for name, values in pooled.items():
            boot[name].append(roc_auc_score(truth[index], values[index]))
    print(f"\n### AUC on the pooled test answers, {args.bootstraps} student bootstraps\n")
    print("| Model | AUC | 95% interval |\n| --- | --- | --- |")
    for name in pooled:
        low, high = np.percentile(boot[name], [2.5, 97.5])
        print(f"| {name} | {point[name]:.4f} | {low:.4f} to {high:.4f} |")
    print("\n### Paired differences (first minus second)\n")
    print("| Pair | Difference | 95% interval | First ahead in |\n| --- | --- | --- | --- |")
    for first, second in PAIRS:
        if first in pooled and second in pooled:
            diff = np.array(boot[first]) - np.array(boot[second])
            low, high = np.percentile(diff, [2.5, 97.5])
            print(f"| {first} - {second} | {point[first] - point[second]:+.4f} | {low:+.4f} to {high:+.4f} | "
                  f"{(diff > 0).mean():.0%} of resamples |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
