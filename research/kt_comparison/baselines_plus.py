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
Only the N training students are used for fitting, counting and choosing; test students never are.

    python baselines_plus.py [--folds 5] [--bootstrap 100] [--students 1500] [--targets assist09,ednet,csedm]
"""
import argparse

import numpy as np
import pandas as pd
from cold_start_plus import (
    GROUPS,
    auc_bootstrap,
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
)
from compare import load_assist09, load_ednet
from scipy import sparse
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

LEVELS = [30, 100, 300, None]
NAMES = ["lms_default", "pfa", "rasch", "gbdt", "stack_transfer", "hybrid"]
SEQUENCE = ("sakt", "sakt_item", "akt_lite")  # sequence_models.py; added to NAMES with --sequence (Python 3.12 + PyTorch)
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


def pfa_predict(sub, test, wins_tr, losses_tr, wins_te, losses_te) -> np.ndarray:
    skills = {s: i for i, s in enumerate(sub["skill_name"].unique())}
    k = len(skills)
    x_tr = pfa_matrix(sub["skill_name"].map(skills).to_numpy(), wins_tr, losses_tr, k)
    x_te = pfa_matrix(test["skill_name"].map(skills).fillna(-1).astype(int).to_numpy(), wins_te, losses_te, k)
    y = sub["correct"].to_numpy()
    users = sub["user_id"].unique()
    held = np.random.default_rng(0).choice(users, size=max(1, len(users) // 5), replace=False)
    is_held = sub["user_id"].isin(held).to_numpy()
    best, best_c = np.inf, PFA_C[1]
    for c in PFA_C:
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


def run(name: str, data: pd.DataFrame, w_transfer: np.ndarray, folds: int, draws: int) -> None:
    data = data.sort_values("order_id").reset_index(drop=True)
    causal_all, lms_all = causal_features(data)
    wins_all, losses_all = pfa_counts(data)
    print(f"{name}: {len(data)} answers, {data.user_id.nunique()} students", flush=True)
    results: dict = {}
    stored: dict = {}
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=folds).split(data, groups=data["user_id"]), 1):
        train, test = data.iloc[tr].reset_index(drop=True), data.iloc[te].reset_index(drop=True)
        truth = test["correct"].to_numpy().astype(float)
        order = np.random.default_rng(fold).permutation(train["user_id"].unique())
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
                "pfa": pfa_predict(sub, test, wins_all[tr][mask], losses_all[tr][mask], wins_all[te], losses_all[te]),
                "rasch": rasch_predict(sub, test),
                "gbdt": gbdt_p,
                "stack_transfer": sigmoid(x_te @ w),
                "hybrid": sigmoid((1 - alpha) * (x_te @ w) + alpha * logit(gbdt_p)),
            }
            for kind in SEQUENCE if SEQUENCE[0] in NAMES else ():
                preds[kind] = sequence_predict(sub, test, kind)
            for label, p in preds.items():
                results.setdefault((level, label), []).append(metrics(truth, p))
            stored.setdefault(level, []).append((te, preds))
            print(f"fold {fold} N={'all' if level is None else level}: "
                  + ", ".join(f"{k} {results[(level, k)][-1]['AUC']:.4f}" for k in NAMES) + f"  alpha {alpha}", flush=True)
    for metric in ("AUC", "ECE", "LogLoss"):
        print(f"\n### {name}: {metric} (mean over folds, std in brackets)\n")
        print("| Training students | " + " | ".join(NAMES) + " |\n| --- | " + " | ".join("---" for _ in NAMES) + " |")
        for level in LEVELS:
            if (level, NAMES[0]) in results:
                cells = [f"{np.mean([r[metric] for r in results[(level, k)]]):.4f} "
                         f"({np.std([r[metric] for r in results[(level, k)]]):.4f})" for k in NAMES]
                print(f"| {'all' if level is None else level} | " + " | ".join(cells) + " |")
    truth_all = data["correct"].to_numpy().astype(float)
    user_rows = pd.Series(np.arange(len(data))).groupby(data["user_id"].to_numpy()).indices
    rng = np.random.default_rng(0)
    for focus in ("stack_transfer", "hybrid"):
        print(f"\n### {name}: AUC difference {focus} minus other model, 95% interval over students "
              f"({draws} resamples)\n\n| Training students | against | difference | interval |\n| --- | --- | --- | --- |")
        for level in (100, None):
            if level not in stored:
                continue
            merged = {k: np.zeros(len(data)) for k in NAMES}
            for te, preds in stored[level]:
                for k in NAMES:
                    merged[k][te] = preds[k]
            for other in [k for k in ("pfa", "rasch", "gbdt", "stack_transfer", *SEQUENCE) if k in NAMES and k != focus]:
                diff = roc_auc_score(truth_all, merged[focus]) - roc_auc_score(truth_all, merged[other])
                low, high = auc_bootstrap(truth_all, (merged[focus], merged[other]), user_rows, draws, rng)
                print(f"| {'all' if level is None else level} | {other} | {diff:+.4f} | {low:+.4f} to {high:+.4f} |")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--bootstrap", type=int, default=100)
    parser.add_argument("--students", type=int, default=1500)
    parser.add_argument("--targets", default="assist09,ednet,csedm")
    parser.add_argument("--ednet-seed", type=int, default=0, help="which random sample of EdNet students (1 = replication)")
    parser.add_argument("--sequence", action="store_true", help="also run sakt, sakt_item and akt_lite (needs PyTorch)")
    args = parser.parse_args()
    if args.sequence:
        global sequence_predict
        from sequence_models import sequence_predict
        NAMES.extend(SEQUENCE)
    loaders = {"assist09": load_assist09, "ednet": lambda: load_ednet(args.students, args.ednet_seed), "csedm": load_csedm}
    datasets = {name: load() for name, load in loaders.items()}
    for name in args.targets.split(","):
        w = transfer_weights([d for k, d in datasets.items() if k != name])
        print(f"\n## {name}\n", flush=True)
        run(name, datasets[name], w, args.folds, args.bootstrap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
