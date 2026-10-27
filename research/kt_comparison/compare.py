"""Next-answer prediction on public knowledge-tracing data: the LMS mastery rule against standard baselines (claim 4).

Each model predicts P(correct) for a student's next answer on a skill before seeing it, from that student's earlier
answers on the same skill. Students are split into folds, so no test student is seen when fitting. Metric: AUC over
every test prediction. Models:
  lms       app.mastery.core.bayes_update with the LMS defaults (prior 0.5, slip 0.10, guess 0.20), nothing fitted
  global    mean correctness of the training answers
  skill     mean correctness per skill in the training answers
  pybkt     pyBKT, one standard BKT model per skill, fitted on the training students

Run in a separate virtual environment (numpy, pandas, scikit-learn, scipy, pyBKT), not in the project's. Datasets are
read from KT_DATA_DIR (default: a Datasets folder beside the repository) and are never committed:
    python compare.py assist09 [--folds 5]
    python compare.py ednet [--students 3000] [--folds 5]
"""
import argparse
import os
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("KT_DATA_DIR", HERE.parents[2] / "Datasets"))  # kept outside the repository
sys.path.insert(0, str(HERE.parents[1] / "backend"))
from app.mastery.core import DEFAULT_PARAMS, bayes_update  # noqa: E402

PRIOR = 0.5
SLIP, GUESS = DEFAULT_PARAMS["all_pass"]


def load_assist09() -> pd.DataFrame:
    raw = pd.read_csv(DATA / "ASSISTments2009" / "skill_builder_data.csv", encoding="latin-1", low_memory=False)
    raw = raw.dropna(subset=["skill_id"])
    frame = pd.DataFrame({
        "user_id": raw["user_id"], "skill_name": raw["skill_id"].astype(str),
        "correct": raw["correct"].astype(int), "order_id": raw["order_id"],
    })
    return frame.sort_values("order_id").reset_index(drop=True)


def load_ednet(students: int, seed: int = 0) -> pd.DataFrame:
    answers = pd.read_csv(DATA / "EdNet" / "contents" / "questions.csv")
    answers["skill_name"] = answers["tags"].astype(str).str.split(";").str[0]
    key = answers.set_index("question_id")[["correct_answer", "skill_name"]]
    archive = zipfile.ZipFile(DATA / "EdNet" / "EdNet-KT1.zip")
    names = [n for n in archive.namelist() if n.endswith(".csv")]
    chosen = np.random.default_rng(seed).choice(len(names), size=min(students, len(names)), replace=False)
    frames = []
    for i in chosen:
        part = pd.read_csv(archive.open(names[i]))
        part["user_id"] = Path(names[i]).stem
        frames.append(part)
    raw = pd.concat(frames, ignore_index=True).join(key, on="question_id", how="inner")
    raw["correct"] = (raw["user_answer"] == raw["correct_answer"]).astype(int)
    raw = raw.sort_values(["timestamp", "solving_id"]).reset_index(drop=True)
    raw["order_id"] = np.arange(len(raw))
    return raw[["user_id", "skill_name", "correct", "order_id"]]


def predict_lms(test: pd.DataFrame) -> np.ndarray:
    out = np.empty(len(test))
    state: dict[tuple, float] = {}
    for position, (user, skill, correct) in enumerate(
        zip(test["user_id"], test["skill_name"], test["correct"], strict=True)
    ):
        p = state.get((user, skill), PRIOR)
        out[position] = p * (1 - SLIP) + (1 - p) * GUESS
        state[(user, skill)] = bayes_update(p, SLIP, GUESS, bool(correct))
    return out


def predict_params(test: pd.DataFrame, prior: float, slip: float, guess: float, learn: float) -> np.ndarray:
    """The LMS update (bayes_update) with chosen numbers, plus an optional BKT-style learning step after each answer."""
    out = np.empty(len(test))
    state: dict[tuple, float] = {}
    for position, (user, skill, correct) in enumerate(
        zip(test["user_id"], test["skill_name"], test["correct"], strict=True)
    ):
        p = state.get((user, skill), prior)
        out[position] = p * (1 - slip) + (1 - p) * guess
        p = bayes_update(p, slip, guess, bool(correct))
        state[(user, skill)] = p + (1 - p) * learn
    return out


def fit_params(
    train: pd.DataFrame, with_learning: bool, sample_students: int = 800
) -> tuple[float, float, float, float]:
    """Numbers that minimise log loss on a sample of training students (the test students are never used)."""
    from scipy.optimize import minimize

    users = train["user_id"].unique()
    chosen = np.random.default_rng(0).choice(users, size=min(sample_students, len(users)), replace=False)
    sample = train[train["user_id"].isin(chosen)].reset_index(drop=True)
    truth = sample["correct"].to_numpy()

    def unpack(x):
        prior, slip, guess = 0.01 + 0.98 / (1 + np.exp(-x[:3]))
        slip, guess = min(slip, 0.5), min(guess, 0.5)
        learn = 0.5 / (1 + np.exp(-x[3])) if with_learning else 0.0
        return prior, slip, guess, learn

    def loss(x):
        predicted = np.clip(predict_params(sample, *unpack(x)), 1e-6, 1 - 1e-6)
        return -np.mean(truth * np.log(predicted) + (1 - truth) * np.log(1 - predicted))

    start = np.array([0.0, -2.0, -1.4, -2.0])
    result = minimize(loss, start, method="Nelder-Mead", options={"maxiter": 250, "xatol": 1e-2, "fatol": 1e-5})
    return unpack(result.x)


def predict_per_skill(train: pd.DataFrame, test: pd.DataFrame, fallback: tuple, min_answers: int = 30) -> np.ndarray:
    """The LMS rule with its own fitted numbers (including a learning step) for each skill; a skill with fewer than
    `min_answers` training answers uses the numbers fitted over all skills."""
    out = np.empty(len(test))
    for skill, rows in test.groupby("skill_name"):
        own = train[train["skill_name"] == skill]
        enough = len(own) >= min_answers and own["correct"].nunique() > 1
        numbers = fit_params(own, with_learning=True) if enough else fallback
        out[rows.index.to_numpy()] = predict_params(rows, *numbers)
    return out


def predict_pybkt(train: pd.DataFrame, test: pd.DataFrame, fallback: float) -> tuple[np.ndarray, int]:
    import re

    import sklearn.metrics as metrics

    # pyBKT probes every scikit-learn metric with plain lists at import and only tolerates a TypeError; this
    # scikit-learn version raises AttributeError for some of them
    def tolerant(function):
        def call(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except AttributeError as exc:
                raise TypeError(str(exc)) from None
        return call

    for module in (metrics._regression, metrics._classification):
        for name in dir(module):
            if re.search("_loss$|_score$|_error$", name):
                setattr(module, name, tolerant(getattr(module, name)))
    from pyBKT.models import Model

    # One model per skill: fitting every skill in a single call gave AUC 0.51 where this gives about 0.70
    parts = []
    for skill, rows in test.groupby("skill_name"):
        fitted = train[train["skill_name"] == skill]
        if fitted["correct"].nunique() < 2:
            continue
        model = Model(parallel=False, seed=0, num_fits=1)
        model.fit(data=fitted)
        parts.append(model.predict(data=rows))
    got = pd.concat(parts).set_index("order_id")["correct_predictions"]
    values = test["order_id"].map(got)
    missing = int(values.isna().sum())
    return values.fillna(fallback).to_numpy(), missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["assist09", "ednet"])
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--students", type=int, default=3000)
    parser.add_argument("--no-bkt", action="store_true")
    parser.add_argument("--fit-skill", action="store_true", help="also fit the LMS rule's numbers for each skill")
    parser.add_argument("--fit", action="store_true", help="also fit the LMS rule's numbers on the training students")
    args = parser.parse_args()
    data = load_assist09() if args.dataset == "assist09" else load_ednet(args.students)
    print(f"{args.dataset}: {len(data)} answers, {data.user_id.nunique()} students, "
          f"{data.skill_name.nunique()} skills, {data.correct.mean():.3f} correct\n", flush=True)
    names = ("lms", "global", "skill", "pybkt", "lms_fit", "lms_fit_learn", "lms_per_skill")
    scores: dict[str, list[float]] = {name: [] for name in names}
    fitted_numbers: list[tuple] = []
    unmatched = 0
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=args.folds).split(data, groups=data["user_id"]), 1):
        train, test = data.iloc[tr], data.iloc[te].reset_index(drop=True)
        base = float(train["correct"].mean())
        by_skill = train.groupby("skill_name")["correct"].mean()
        truth = test["correct"].to_numpy()
        scores["lms"].append(roc_auc_score(truth, predict_lms(test)))
        scores["global"].append(0.5)
        scores["skill"].append(roc_auc_score(truth, test["skill_name"].map(by_skill).fillna(base).to_numpy()))
        if args.fit:
            numbers = fit_params(train, with_learning=False)
            with_learning = fit_params(train, with_learning=True)
            fitted_numbers.append((numbers, with_learning))
            scores["lms_fit"].append(roc_auc_score(truth, predict_params(test, *numbers)))
            scores["lms_fit_learn"].append(roc_auc_score(truth, predict_params(test, *with_learning)))
        if args.fit_skill:
            overall = fit_params(train, with_learning=True)
            scores["lms_per_skill"].append(roc_auc_score(truth, predict_per_skill(train, test, overall)))
        if not args.no_bkt:
            values, missing = predict_pybkt(train, test, base)
            unmatched += missing
            scores["pybkt"].append(roc_auc_score(truth, values))
        print(f"fold {fold}: " + ", ".join(f"{k} {v[-1]:.4f}" for k, v in scores.items() if v), flush=True)
    print("\n| Model | Mean AUC | Std over folds |\n| --- | --- | --- |")
    labels = {"lms": "LMS mastery rule (nothing fitted)", "global": "global mean (constant)",
              "skill": "per-skill mean", "pybkt": "pyBKT, standard BKT per skill",
              "lms_fit": "LMS rule, prior/slip/guess fitted (no learning step)",
              "lms_fit_learn": "LMS rule, prior/slip/guess fitted + learning step",
              "lms_per_skill": "LMS rule, numbers fitted per skill (with learning step)"}
    for key, values in scores.items():
        if values:
            print(f"| {labels[key]} | {np.mean(values):.4f} | {np.std(values):.4f} |")
    if unmatched:
        print(f"\npyBKT returned no prediction for {unmatched} test answers; they were given the training mean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
