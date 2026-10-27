"""Cold start and calibration: how do the LMS rule's predictions compare when little or no training data exists?

For each fold the training students are shuffled and the first N of them are used to fit the models; the test students
are always the same. Models:
  lms_default   the LMS rule with its default numbers, needs no data (same at every N)
  skill_mean    per-skill mean correctness of the N training students (0.5 when N = 0)
  lms_fitted    the LMS rule with numbers fitted per skill, for a skill with at least 30 training answers and both
                outcomes; any other skill keeps the defaults
Metrics on the test students: AUC, Brier score, log loss and expected calibration error (10 equal-width bins).
Lower is better for the last three.

    python cold_start.py assist09 [--folds 3]
    python cold_start.py ednet [--students 1500] [--folds 3]
"""
import argparse

import numpy as np
import pandas as pd
from compare import GUESS, PRIOR, SLIP, fit_params, load_assist09, load_ednet, predict_lms, predict_params
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

LEVELS = [0, 10, 30, 100, 300, None]  # None: every training student
MIN_ANSWERS = 30
DEFAULTS = (PRIOR, SLIP, GUESS, 0.0)


def metrics(truth: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    p = np.clip(predicted, 1e-6, 1 - 1e-6)
    bins = np.minimum((p * 10).astype(int), 9)
    ece = 0.0
    for b in range(10):
        chosen = bins == b
        if chosen.any():
            ece += chosen.mean() * abs(p[chosen].mean() - truth[chosen].mean())
    return {
        "AUC": roc_auc_score(truth, p), "Brier": float(np.mean((p - truth) ** 2)),
        "LogLoss": float(-np.mean(truth * np.log(p) + (1 - truth) * np.log(1 - p))), "ECE": float(ece),
    }


def skill_mean_predict(sub: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    base = float(sub["correct"].mean()) if len(sub) else 0.5
    if not len(sub):
        return np.full(len(test), base)
    return test["skill_name"].map(sub.groupby("skill_name")["correct"].mean()).fillna(base).to_numpy()


def fitted_predict(sub: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    out = np.empty(len(test))
    for skill, rows in test.groupby("skill_name"):
        own = sub[sub["skill_name"] == skill]
        numbers = fit_params(own, with_learning=True) if len(own) >= MIN_ANSWERS and own["correct"].nunique() > 1 \
            else DEFAULTS
        out[rows.index.to_numpy()] = predict_params(rows, *numbers)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["assist09", "ednet"])
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--students", type=int, default=1500)
    args = parser.parse_args()
    data = load_assist09() if args.dataset == "assist09" else load_ednet(args.students)
    print(f"{args.dataset}: {len(data)} answers, {data.user_id.nunique()} students, "
          f"{data.skill_name.nunique()} skills\n", flush=True)
    results: dict[tuple, list[dict]] = {}
    reliability = {"lms_default": [], "lms_fitted (all training students)": []}
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=args.folds).split(data, groups=data["user_id"]), 1):
        train, test = data.iloc[tr], data.iloc[te].reset_index(drop=True)
        truth = test["correct"].to_numpy().astype(float)
        default = predict_lms(test)
        order = np.random.default_rng(fold).permutation(train["user_id"].unique())
        for level in LEVELS:
            chosen = order if level is None else order[:level]
            sub = train[train["user_id"].isin(chosen)]
            predictions = {"lms_default": default, "skill_mean": skill_mean_predict(sub, test),
                           "lms_fitted": fitted_predict(sub, test)}
            for name, predicted in predictions.items():
                results.setdefault((level, name), []).append(metrics(truth, predicted))
            print(f"fold {fold} N={'all' if level is None else level}: "
                  + ", ".join(f"{n} {results[(level, n)][-1]['AUC']:.4f}" for n in predictions), flush=True)
            if level is None and fold == 1:
                for label, predicted in (("lms_default", default),
                                         ("lms_fitted (all training students)", predictions["lms_fitted"])):
                    bins = np.minimum((predicted * 10).astype(int), 9)
                    reliability[label] = [(b, int((bins == b).sum()), float(predicted[bins == b].mean()),
                                           float(truth[bins == b].mean())) for b in range(10) if (bins == b).any()]
    for metric in ("AUC", "Brier", "LogLoss", "ECE"):
        print(f"\n### {metric} (mean over folds, std in brackets)\n")
        print("| Training students | LMS default | per-skill mean | LMS fitted per skill |\n| --- | --- | --- | --- |")
        for level in LEVELS:
            cells = []
            for name in ("lms_default", "skill_mean", "lms_fitted"):
                values = [r[metric] for r in results[(level, name)]]
                cells.append(f"{np.mean(values):.4f} ({np.std(values):.4f})")
            print(f"| {'all' if level is None else level} | " + " | ".join(cells) + " |")
    for label, rows in reliability.items():
        print(f"\n### Reliability, fold 1: {label}\n\n| Predicted bin | Answers | Mean predicted | Observed correct |\n"
              "| --- | --- | --- | --- |")
        for b, count, mean_predicted, observed in rows:
            print(f"| {b / 10:.1f}-{(b + 1) / 10:.1f} | {count} | {mean_predicted:.3f} | {observed:.3f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
