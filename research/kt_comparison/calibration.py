"""Can a cheap correction make the LMS rule's next-answer predictions honest probabilities? (TR-M-01, research only)

The rule with its default numbers ranks answers well but is badly calibrated (ECE about 0.14). Here a monotone map from
the rule's prediction to the observed rate of correct answers is fitted on N training students and applied to the test
students; the rule itself is not changed. Two maps: Platt (a logistic fit on the logit of the prediction, which keeps the
ranking and so the AUC) and isotonic regression (which can merge ranks and so lose a little AUC).

Success rule, fixed before the run: a map counts as a success on a dataset if, averaged over the folds with every training
student, the calibrated ECE is at most 0.05 and the AUC is at most 0.005 below the uncalibrated rule's.

    python calibration.py assist09 [--folds 3]
    python calibration.py ednet [--students 1500] [--folds 3]
"""
import argparse

import numpy as np
from cold_start import metrics
from compare import load_assist09, load_ednet, predict_lms
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

LEVELS = [10, 30, 100, 300, None]
MAX_ECE = 0.05
MAX_AUC_LOSS = 0.005


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def fit_maps(predicted: np.ndarray, truth: np.ndarray):
    platt = LogisticRegression(C=1e6).fit(logit(predicted), truth)
    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(predicted, truth)
    return (lambda p: platt.predict_proba(logit(p))[:, 1]), (lambda p: isotonic.predict(p))


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
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=args.folds).split(data, groups=data["user_id"]), 1):
        train, test = data.iloc[tr].reset_index(drop=True), data.iloc[te].reset_index(drop=True)
        truth = test["correct"].to_numpy().astype(float)
        raw_test = predict_lms(test)
        raw_train = predict_lms(train)
        train_truth = train["correct"].to_numpy().astype(float)
        results.setdefault((None, "uncalibrated"), []).append(metrics(truth, raw_test))
        order = np.random.default_rng(fold).permutation(train["user_id"].unique())
        for level in LEVELS:
            chosen = train["user_id"].isin(order if level is None else order[:level]).to_numpy()
            platt, isotonic = fit_maps(raw_train[chosen], train_truth[chosen])
            results.setdefault((level, "Platt"), []).append(metrics(truth, platt(raw_test)))
            results.setdefault((level, "isotonic"), []).append(metrics(truth, isotonic(raw_test)))
        print(f"fold {fold} done", flush=True)

    def cell(key, metric):
        values = [r[metric] for r in results[key]]
        return f"{np.mean(values):.4f} ({np.std(values):.4f})"

    for metric in ("ECE", "AUC", "LogLoss", "Brier"):
        print(f"\n### {metric} (mean over folds, std in brackets)\n")
        print("| Training students for the map | uncalibrated | Platt | isotonic |\n| --- | --- | --- | --- |")
        for level in LEVELS:
            print(f"| {'all' if level is None else level} | {cell((None, 'uncalibrated'), metric)} | "
                  f"{cell((level, 'Platt'), metric)} | {cell((level, 'isotonic'), metric)} |")
    base_auc = np.mean([r["AUC"] for r in results[(None, "uncalibrated")]])
    print("\n### Success rule (every training student)\n")
    for name in ("Platt", "isotonic"):
        ece = np.mean([r["ECE"] for r in results[(None, name)]])
        auc = np.mean([r["AUC"] for r in results[(None, name)]])
        ok = ece <= MAX_ECE and base_auc - auc <= MAX_AUC_LOSS
        print(f"- {name}: ECE {ece:.4f} (limit {MAX_ECE}), AUC change {auc - base_auc:+.4f} "
              f"(allowed loss {MAX_AUC_LOSS}): {'SUCCESS' if ok else 'NOT a success'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
