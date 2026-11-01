"""Stronger baselines for the cold-start stack of cold_start_plus.py (TR-V-05), on the same folds and the same N.

  stack_transfer  the stack of cold_start_plus.py (starts from weights fitted on the other datasets)
  pfa             Performance Factors Analysis: logistic regression on skill indicators and, per skill, the log of the
                  student's earlier successes and of earlier failures on it; C chosen on a held-out fifth of the N students
  rasch           one-parameter item-response model: student and item indicators, fitted by L2 logistic regression
                  (C = 1); a test student's ability is re-estimated after every answer from their own earlier answers
                  only (MAP, prior variance C), and an item unseen in training gets the average item effect
  gbdt            gradient-boosted trees (scikit-learn HistGradientBoosting) on the stack's six features
  hybrid          post-hoc (added after the first run showed gbdt ahead at large N): a blend of the stack's and gbdt's
                  logits; the blend weight is chosen on out-of-group predictions of the N training students only
  sakt, sakt_item, akt_lite   sequence models of sequence_models.py, with --sequence
  lms_default     the LMS rule with its default numbers
  stack_flat, rule_platt, drop_*   controls, with --controls (step 95): the stack without transfer (prior weights 0), the rule with a
                  Platt map fitted on the other datasets, and the transfer stack with one feature left out
Only the N training students are used for fitting, counting and choosing; test students never are.

    python baselines_plus.py [--folds 5] [--bootstrap 100] [--students 1500] [--targets assist09,ednet,csedm]
"""
import argparse
import os

import numpy as np
import pandas as pd
from cold_start_plus import (
    GROUPS,
    causal_features,
    choose_and_fit,
    course_features,
    design,
    load_csedm,
    metrics,
    sigmoid,
    logit,
    ridge_fit,
    transfer_weights,
    dataset_matrix,
)
from compare import load_assist09, load_ednet
from scipy import sparse
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from tuning import PFA_C_TUNED, PUBLISHED_SETTINGS, SEQUENCE_SETTINGS, tuned_gbdt, tuned_rasch_c

LEVELS = [30, 100, 300, None]
NAMES = ["lms_default", "pfa", "rasch", "gbdt", "stack_transfer", "hybrid"]
PUBLISHED = ("dkt", "akt")  # published_models.py (pyKT DKT and AKT); with --published, only at N in PUBLISHED_LEVELS
PUBLISHED_LEVELS = (30, 100, None)
ORDER_SEED = 0  # --order-seed: which random order of the training students; 0 is the run of step 92
SKIP: set = set()  # --skip: models left out (to save time in repeated runs)
PLACEBO = False  # --placebo: labels permuted across all answers; every model should then score about 0.5
TUNED = ("gbdt_tuned", "pfa_tuned", "rasch_tuned")  # tuning.py; added to NAMES with --tune
SEQUENCE = ("sakt", "sakt_item", "akt_lite")  # sequence_models.py; added to NAMES with --sequence (Python 3.12 + PyTorch)
CONTROLS = ("stack_flat", "rule_platt", "drop_rule", "drop_student", "drop_count", "drop_recent", "drop_skill", "drop_item")
PRIORS: dict = {}  # --controls: "platt" weights on (rule logit, intercept) and "drop" priors, one per left-out feature
ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0]  # weight of gbdt in the hybrid
MIN_HYBRID_ROWS = 200
PFA_C = [0.1, 1.0, 10.0]


def pfa_counts(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Earlier successes and failures of the same student on the same skill (rows in time order)."""
    wins = np.zeros(len(frame))
    losses = np.zeros(len(frame))
    seen: dict[tuple, list[int]] = {}
    for i, (user, skill, correct) in enumerate(zip(frame["user_id"], frame["skill_name"], frame["correct"], strict=True)):
        w, f = seen.get((user, skill), (0, 0))
        wins[i], losses[i] = w, f
        seen[(user, skill)] = [w + int(correct), f + int(not correct)]
    return np.log1p(wins), np.log1p(losses)


def pfa_matrix(skill_index: np.ndarray, wins: np.ndarray, losses: np.ndarray, skills: int) -> sparse.csr_matrix:
    rows = np.arange(len(skill_index))
    known = skill_index >= 0
    rows, idx, w, f = rows[known], skill_index[known], wins[known], losses[known]
    data = np.concatenate([np.ones(len(rows)), w, f])
    cols = np.concatenate([idx, skills + idx, 2 * skills + idx])
    return sparse.csr_matrix((data, (np.concatenate([rows] * 3), cols)), shape=(len(skill_index), 3 * skills))


def pfa_predict(sub, test, wins_tr, losses_tr, wins_te, losses_te, c_grid=None) -> np.ndarray:
    skills = {s: i for i, s in enumerate(sub["skill_name"].unique())}
    k = len(skills)
    x_tr = pfa_matrix(sub["skill_name"].map(skills).to_numpy(), wins_tr, losses_tr, k)
    x_te = pfa_matrix(test["skill_name"].map(skills).fillna(-1).astype(int).to_numpy(), wins_te, losses_te, k)
    y = sub["correct"].to_numpy()
    users = sub["user_id"].unique()
    held = np.random.default_rng(0).choice(users, size=max(1, len(users) // 5), replace=False)
    is_held = sub["user_id"].isin(held).to_numpy()
    c_grid = c_grid or PFA_C
    best, best_c = np.inf, c_grid[len(c_grid) // 2]
    for c in c_grid:
        fit = LogisticRegression(C=c, max_iter=300).fit(x_tr[~is_held], y[~is_held])
        p = np.clip(fit.predict_proba(x_tr[is_held])[:, 1], 1e-6, 1 - 1e-6)
        loss = -np.mean(y[is_held] * np.log(p) + (1 - y[is_held]) * np.log(1 - p))
        if loss < best:
            best, best_c = loss, c
    return LogisticRegression(C=best_c, max_iter=300).fit(x_tr, y).predict_proba(x_te)[:, 1]


def rasch_predict(sub: pd.DataFrame, test: pd.DataFrame, c: float = 1.0) -> np.ndarray:
    users = {u: i for i, u in enumerate(sub["user_id"].unique())}
    items = {s: i for i, s in enumerate(sub["item_id"].unique())}
    u_idx, i_idx = sub["user_id"].map(users).to_numpy(), sub["item_id"].map(items).to_numpy()
    rows = np.arange(len(sub))
    x = sparse.csr_matrix((np.ones(2 * len(sub)), (np.concatenate([rows, rows]), np.concatenate([u_idx, len(users) + i_idx]))),
                          shape=(len(sub), len(users) + len(items)))
    fit = LogisticRegression(C=c, max_iter=300).fit(x, sub["correct"].to_numpy())
    intercept = float(fit.intercept_[0])
    easiness = fit.coef_[0][len(users):]
    v = test["item_id"].map(items).map(lambda i: easiness[int(i)] if i == i else 0.0).to_numpy(dtype=float)
    y = test["correct"].to_numpy().astype(float)
    out = np.empty(len(test))
    for rows_of in pd.Series(np.arange(len(test))).groupby(test["user_id"].to_numpy()).indices.values():
        theta = 0.0
        for t, row in enumerate(rows_of):
            if t:
                shift = intercept + v[rows_of[:t]]
                for _ in range(3):
                    p = sigmoid(theta + shift)
                    gradient = np.sum(y[rows_of[:t]] - p) - theta / c
                    curvature = np.sum(p * (1 - p)) + 1 / c
                    theta += gradient / curvature
            out[row] = sigmoid(intercept + theta + v[row])
    return out


def make_gbdt() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, early_stopping=True, random_state=0)


def hybrid_alpha(x: np.ndarray, y: np.ndarray, group: np.ndarray, w0: np.ndarray, lam: float | None) -> float:
    """Weight of gbdt in the blend, from out-of-group predictions of both models on the training students."""
    stack_logit, gbdt_logit = np.empty(len(y)), np.empty(len(y))
    for g in range(GROUPS):
        held = group == g
        if not held.any() or held.all():
            return 0.0
        w = w0 if lam is None else ridge_fit(x[~held], y[~held], w0, lam)
        stack_logit[held] = x[held] @ w
        gbdt_logit[held] = logit(make_gbdt().fit(x[~held][:, :6], y[~held]).predict_proba(x[held][:, :6])[:, 1])

    def loss(alpha: float) -> float:
        z = (1 - alpha) * stack_logit + alpha * gbdt_logit
        return float(np.sum(np.logaddexp(0, z) - y * z))

    return min(ALPHAS, key=loss)


def run(name: str, data: pd.DataFrame, w_transfer: np.ndarray, folds: int, draws: int, save_dir: str | None = None) -> None:
    data = data.sort_values("order_id").reset_index(drop=True)
    if PLACEBO:
        data["correct"] = np.random.default_rng(0).permutation(data["correct"].to_numpy())
    causal_all, lms_all = causal_features(data)
    wins_all, losses_all = pfa_counts(data)
    print(f"{name}: {len(data)} answers, {data.user_id.nunique()} students", flush=True)
    results: dict = {}
    stored: dict = {}
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=folds).split(data, groups=data["user_id"]), 1):
        train, test = data.iloc[tr].reset_index(drop=True), data.iloc[te].reset_index(drop=True)
        truth = test["correct"].to_numpy().astype(float)
        order = np.random.default_rng(fold + 1000 * ORDER_SEED).permutation(train["user_id"].unique())
        for level in LEVELS:
            if level is not None and level >= len(order):
                continue
            chosen = order if level is None else order[:level]
            mask = train["user_id"].isin(chosen).to_numpy()
            sub = train[mask].reset_index(drop=True)
            y = sub["correct"].to_numpy().astype(float)
            group_of = dict(zip(chosen, np.random.default_rng(fold + 100).integers(0, GROUPS, len(chosen)), strict=True))
            group = sub["user_id"].map(group_of).to_numpy()
            skill_tr, item_tr, _ = course_features(sub, sub.assign(_group=group), group)
            skill_te, item_te, _ = course_features(test, sub)
            x_tr = design(causal_all[tr][mask], skill_tr, item_tr)
            x_te = design(causal_all[te], skill_te, item_te)
            w, lam = choose_and_fit(x_tr, y, group, w_transfer)
            gbdt = make_gbdt().fit(x_tr[:, :6], y)
            alpha = hybrid_alpha(x_tr, y, group, w_transfer, lam) if len(sub) >= MIN_HYBRID_ROWS else 0.0
            gbdt_p = gbdt.predict_proba(x_te[:, :6])[:, 1]
            preds = {
                "lms_default": lms_all[te],
                "pfa": None if "pfa" in SKIP else pfa_predict(
                    sub, test, wins_all[tr][mask], losses_all[tr][mask], wins_all[te], losses_all[te]),
                "rasch": None if "rasch" in SKIP else rasch_predict(sub, test),
                "gbdt": gbdt_p,
                "stack_transfer": sigmoid(x_te @ w),
                "hybrid": sigmoid((1 - alpha) * (x_te @ w) + alpha * logit(gbdt_p)),
            }
            if TUNED[0] in NAMES:
                preds["gbdt_tuned"] = tuned_gbdt(x_tr[:, :6], y, sub["user_id"].to_numpy()).predict_proba(x_te[:, :6])[:, 1]
                preds["pfa_tuned"] = pfa_predict(sub, test, wins_all[tr][mask], losses_all[tr][mask], wins_all[te], losses_all[te],
                                                 PFA_C_TUNED)
                preds["rasch_tuned"] = rasch_predict(sub, test, tuned_rasch_c(sub, rasch_predict))
            if CONTROLS[0] in NAMES:
                preds["stack_flat"] = sigmoid(x_te @ choose_and_fit(x_tr, y, group, np.zeros(x_tr.shape[1]))[0])
                preds["rule_platt"] = sigmoid(x_te[:, [0, 6]] @ PRIORS["platt"])
                for k, label in enumerate(CONTROLS[2:]):
                    keep = np.arange(x_tr.shape[1]) != k
                    w_drop = choose_and_fit(x_tr * keep, y, group, PRIORS["drop"][k])[0]
                    preds[label] = sigmoid((x_te * keep) @ w_drop)
            preds = {k: v for k, v in preds.items() if v is not None}
            for kind in SEQUENCE if SEQUENCE[0] in NAMES else ():
                if kind in NAMES:
                    preds[kind] = sequence_predict(sub, test, kind)
                if f"{kind}_tuned" in NAMES:
                    preds[f"{kind}_tuned"] = sequence_predict(sub, test, kind, settings=SEQUENCE_SETTINGS)
            if level in PUBLISHED_LEVELS:
                for kind in PUBLISHED:
                    if kind in NAMES:
                        preds[kind] = published_predict(sub, test, kind)
                    if f"{kind}_tuned" in NAMES:
                        preds[f"{kind}_tuned"] = published_predict(sub, test, kind, settings=PUBLISHED_SETTINGS)
            for label, p in preds.items():
                results.setdefault((level, label), []).append(metrics(truth, p))
            stored.setdefault(level, []).append((te, preds))
            if save_dir:
                np.savez_compressed(f"{save_dir}/{name}_fold{fold}_N{'all' if level is None else level}.npz", rows=te, **preds)
            print(f"fold {fold} N={'all' if level is None else level}: "
                  + ", ".join(f"{k} {results[(level, k)][-1]['AUC']:.4f}" for k in NAMES if k in preds) + f"  alpha {alpha}", flush=True)
    for metric in ("AUC", "ECE", "LogLoss"):
        print(f"\n### {name}: {metric} (mean over folds, std in brackets)\n")
        print("| Training students | " + " | ".join(NAMES) + " |\n| --- | " + " | ".join("---" for _ in NAMES) + " |")
        for level in LEVELS:
            if (level, NAMES[0]) in results:
                cells = [f"{np.mean([r[metric] for r in results[(level, k)]]):.4f} "
                         f"({np.std([r[metric] for r in results[(level, k)]]):.4f})" if (level, k) in results else "-"
                         for k in NAMES]
                print(f"| {'all' if level is None else level} | " + " | ".join(cells) + " |")
    truth_all = data["correct"].to_numpy().astype(float)
    user_rows = pd.Series(np.arange(len(data))).groupby(data["user_id"].to_numpy()).indices
    rng = np.random.default_rng(0)
    focuses = ("stack_transfer", "hybrid")
    pairs = [k for k in ("pfa", "rasch", "gbdt", "stack_transfer", *TUNED, *SEQUENCE, *PUBLISHED, *CONTROLS)]
    boot: dict = {}
    for level in (30, 100, None):
        if level not in stored:
            continue
        present = [k for k in NAMES if k in stored[level][0][1]]
        merged = {k: np.zeros(len(data)) for k in present}
        for te, preds in stored[level]:
            for k in present:
                merged[k][te] = preds[k]
        boot[level] = (merged, {k: fast_auc(truth_all, merged[k]) for k in present}, bootstrap_aucs(truth_all, merged, user_rows, draws, rng))
    for focus in focuses:
        print(f"\n### {name}: AUC difference {focus} minus other model, 95% interval over students "
              f"({draws} resamples)\n\n| Training students | against | difference | interval |\n| --- | --- | --- | --- |")
        for level, (merged, point, resampled) in boot.items():
            for other in [k for k in pairs if k in merged and k != focus]:
                low, high = np.percentile(resampled[focus] - resampled[other], [2.5, 97.5])
                print(f"| {'all' if level is None else level} | {other} | {point[focus] - point[other]:+.4f} | {low:+.4f} to {high:+.4f} |")


def fast_auc(truth: np.ndarray, score: np.ndarray) -> float:
    ranks = rankdata(score)
    positives = int(truth.sum())
    return float((ranks[truth == 1].sum() - positives * (positives + 1) / 2) / (positives * (len(truth) - positives)))


def bootstrap_aucs(truth, predictions: dict, user_rows, draws, rng) -> dict:
    """AUC of every model on each of `draws` resamples of whole students; one resample is shared by all models, so differences are paired."""
    keys = list(user_rows)
    out: dict = {k: [] for k in predictions}
    for _ in range(draws):
        rows = np.concatenate([user_rows[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
        if len(set(truth[rows])) < 2:
            continue
        for k, p in predictions.items():
            out[k].append(fast_auc(truth[rows], p[rows]))
    return {k: np.array(v) for k, v in out.items()}


def control_priors(others: list[pd.DataFrame]) -> dict:
    """Priors of the controls, fitted on the other datasets like transfer_weights: a Platt map of the rule's logit, and the stack's
    weights refitted without each of the six features in turn."""
    parts = [dataset_matrix(d) for d in others]
    x = np.vstack([p[0] for p in parts])
    y = np.concatenate([p[1] for p in parts])
    weights = np.concatenate([np.full(len(p[1]), 1 / len(p[1])) for p in parts]) * len(y) / len(parts)
    start = np.array([1.0, 0, 0, 0, 0, 0, 0])
    drop = [ridge_fit(x * (np.arange(x.shape[1]) != k), y, start * (np.arange(x.shape[1]) != k), 1e-3, weights) for k in range(6)]
    return {"platt": ridge_fit(x[:, [0, 6]], y, np.array([1.0, 0.0]), 1e-3, weights), "drop": drop}


def print_zero_data_ablation(data: pd.DataFrame, w_full: np.ndarray) -> None:
    """AUC with no course data (N = 0, course features neutral) of the transfer stack and of each leave-one-feature-out prior."""
    data = data.sort_values("order_id").reset_index(drop=True)
    causal, lms = causal_features(data)
    x = design(causal, np.zeros(len(data)), np.zeros(len(data)))
    truth = data["correct"].to_numpy().astype(float)
    cells = {"lms_default": roc_auc_score(truth, lms), "stack_transfer": roc_auc_score(truth, x @ w_full)}
    for k, label in enumerate(CONTROLS[2:]):
        cells[label] = roc_auc_score(truth, (x * (np.arange(7) != k)) @ PRIORS["drop"][k])
    print("\nN = 0, AUC over all answers (no folds, nothing fitted on this dataset): "
          + ", ".join(f"{k} {v:.4f}" for k, v in cells.items()), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--bootstrap", type=int, default=100)
    parser.add_argument("--students", type=int, default=1500)
    parser.add_argument("--targets", default="assist09,ednet,csedm")
    parser.add_argument("--ednet-seed", type=int, default=0, help="which random sample of EdNet students (1 = replication)")
    parser.add_argument("--sequence", action="store_true", help="also run sakt, sakt_item and akt_lite (needs PyTorch)")
    parser.add_argument("--published", action="store_true", help="also run the pyKT DKT and AKT (needs PyTorch and pykt-toolkit)")
    parser.add_argument("--order-seed", type=int, default=0, help="seed of the order of training students (0 = step 92)")
    parser.add_argument("--skip", default="", help="comma-separated models to leave out, for example pfa,rasch")
    parser.add_argument("--levels", default="", help="comma-separated training sizes, for example 30,100,all")
    parser.add_argument("--half", type=int, default=-1, help="0 or 1: run on a random half of the target dataset's students")
    parser.add_argument("--tune", action="store_true", help="also run gbdt, PFA and Rasch tuned with the declared budget (tuning.py)")
    parser.add_argument("--neural-tuned", default="", help="comma-separated neural models to also run tuned, for example dkt,akt "
                        "(each also needs --published or --sequence for its code to load; the untuned runs can be left out with --skip)")
    parser.add_argument("--controls", action="store_true", help="also run the transfer controls and the leave-one-feature-out stacks")
    parser.add_argument("--placebo", action="store_true", help="permute the labels across all answers (leak check)")
    parser.add_argument("--save", default=None, help="directory for each fold's test predictions (npz)")
    args = parser.parse_args()
    global ORDER_SEED, PLACEBO, LEVELS
    ORDER_SEED, PLACEBO = args.order_seed, args.placebo
    SKIP.update(x for x in args.skip.split(",") if x)
    for skipped in SKIP:
        NAMES.remove(skipped)
    if args.levels:
        LEVELS = [None if x == "all" else int(x) for x in args.levels.split(",")]
    if args.tune:
        NAMES.extend(TUNED)
    if args.published:
        global published_predict
        from published_models import published_predict
        NAMES.extend(PUBLISHED)
    if args.save:
        os.makedirs(args.save, exist_ok=True)
    if args.sequence:
        global sequence_predict
        from sequence_models import sequence_predict
        NAMES.extend(SEQUENCE)
    if args.controls:
        NAMES.extend(CONTROLS)
    if args.neural_tuned:
        NAMES.extend(f"{m}_tuned" for m in args.neural_tuned.split(","))
    loaders = {"assist09": load_assist09, "ednet": lambda: load_ednet(args.students, args.ednet_seed), "csedm": load_csedm}
    datasets = {name: load() for name, load in loaders.items()}
    for name in args.targets.split(","):
        others = [d for k, d in datasets.items() if k != name]
        w = transfer_weights(others)
        if args.controls:
            PRIORS.update(control_priors(others))
            print_zero_data_ablation(datasets[name], w)
        print(f"\n## {name}\n", flush=True)
        target = datasets[name]
        if args.half >= 0:
            users = np.sort(target["user_id"].unique())
            chosen = np.random.default_rng(0).permutation(users)[args.half::2]
            target = target[target["user_id"].isin(chosen)]
        run(name, target, w, args.folds, args.bootstrap, args.save)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
