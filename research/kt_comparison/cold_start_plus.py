"""Cold start: a stacked predictor that starts from weights learned on other datasets and adapts as course data arrives.

Task (as in compare.py): predict P(correct) of a student's next answer from earlier answers. Models, all causal:
  lms_default     the LMS mastery rule with its default numbers; needs no data
  skill_mean      per-skill mean of the N training students
  item_mean       item mean of the N training students, shrunk to its skill mean, then to the overall mean
  stack_plain     logistic stack of the features below, ridge-pulled toward "the LMS default alone"
  stack_transfer  the same stack, ridge-pulled toward weights fitted on the OTHER datasets (so it needs no course data)
  stack_no_lms    ablation: stack_transfer with the LMS rule's feature removed
Features (logits): the LMS rule's prediction, the student's smoothed accuracy over all skills so far, log count of the
student's earlier answers on this skill, the student's last five answers, the skill effect and the item effect from the
N training students (both 0 when N = 0). The ridge strength is chosen by grouped cross-validation inside the N training
students; "pulled to the prior weights" is one of its choices, so the stack cannot fit worse than its prior by that
criterion. Test students are never used for fitting, counting or choosing. Counts for the training rows come from the other
groups of training students, never from a row's own student.

Constants below are declared before any result and were not tuned on test students.

    python cold_start_plus.py [--folds 5] [--bootstrap 100] [--students 1500] [--targets assist09,ednet,csedm]
"""
import argparse
from collections import deque

import numpy as np
import pandas as pd
from compare import DATA, GUESS, PRIOR, SLIP, bayes_update, load_assist09, load_ednet
from scipy.optimize import minimize
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

BASE0 = 0.55  # the default rule's prediction at its prior: 0.5 * (1 - SLIP) + 0.5 * GUESS
M_STUDENT, M_RECENT, M_GLOBAL, M_SKILL, M_ITEM = 3.0, 2.0, 50.0, 20.0, 10.0
LEVELS = [0, 10, 30, 100, 300, 1000, None]  # training students; None: every training student
LAMBDAS = [1e-1, 1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6]  # in units of training answers
GROUPS = 5
NAMES = ("lms_default", "skill_mean", "item_mean", "stack_plain", "stack_transfer", "stack_no_lms")
BUCKETS = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 20), (21, 10**9)]


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


def load_csedm() -> pd.DataFrame:
    """First run of each student on each problem: correct when every test passed (Score 1.0). A skill is one assignment."""
    columns = ["SubjectID", "ServerTimestamp", "CourseID", "AssignmentID", "ProblemID", "EventType", "Score", "EventID"]
    raw = pd.read_csv(DATA / "CSEDM" / "Data" / "MainTable.csv", usecols=columns, low_memory=False)
    runs = raw[(raw["EventType"] == "Run.Program") & raw["Score"].notna()]
    runs = runs.sort_values(["ServerTimestamp", "EventID"]).drop_duplicates(
        ["SubjectID", "CourseID", "AssignmentID", "ProblemID"])
    frame = pd.DataFrame({
        "user_id": runs["SubjectID"].to_numpy(),
        "skill_name": (runs["CourseID"].astype(str) + ":" + runs["AssignmentID"].astype(str)).to_numpy(),
        "item_id": (runs["AssignmentID"].astype(str) + ":" + runs["ProblemID"].astype(str)).to_numpy(),
        "correct": (runs["Score"] >= 1.0).astype(int).to_numpy(),
    })
    frame["order_id"] = np.arange(len(frame))
    return frame


def causal_features(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Four logit features per answer and the raw LMS prediction, from that student's own earlier answers only (rows must be in time order)."""
    n = len(frame)
    out = np.empty((n, 4))
    state: dict[tuple, float] = {}
    seen: dict[tuple, int] = {}
    totals: dict[str, list[int]] = {}
    recent: dict[str, deque] = {}
    for i, (user, skill, correct) in enumerate(zip(frame["user_id"], frame["skill_name"], frame["correct"], strict=True)):
        p = state.get((user, skill), PRIOR)
        right, count = totals.get(user, (0, 0))
        last = recent.get(user)
        window = (sum(last) if last else 0, len(last) if last else 0)
        out[i] = (p * (1 - SLIP) + (1 - p) * GUESS, (right + M_STUDENT * BASE0) / (count + M_STUDENT),
                  seen.get((user, skill), 0), (window[0] + M_RECENT * BASE0) / (window[1] + M_RECENT))
        state[(user, skill)] = bayes_update(p, SLIP, GUESS, bool(correct))
        seen[(user, skill)] = seen.get((user, skill), 0) + 1
        totals[user] = [right + int(correct), count + 1]
        recent.setdefault(user, deque(maxlen=5)).append(int(correct))
    return np.column_stack([logit(out[:, 0]), logit(out[:, 1]), np.log1p(out[:, 2]), logit(out[:, 3])]), out[:, 0]


def course_features(rows: pd.DataFrame, ref: pd.DataFrame, own_group: np.ndarray | None = None):
    """(skill effect, item effect, item estimate) from the reference students' answers. With `own_group`, the reference
    answers of each row's own group are left out. With no reference answers all three are neutral."""
    if not len(ref):
        return np.zeros(len(rows)), np.zeros(len(rows)), np.full(len(rows), BASE0)
    base = (ref["correct"].sum() + M_GLOBAL * BASE0) / (len(ref) + M_GLOBAL)

    def counts(keys: list[str]) -> tuple[np.ndarray, np.ndarray]:
        grouped = ref.groupby(keys)["correct"].agg(["sum", "count"])
        index = pd.MultiIndex.from_frame(rows[keys]) if len(keys) > 1 else pd.Index(rows[keys[0]])
        right = grouped["sum"].reindex(index).fillna(0).to_numpy()
        total = grouped["count"].reindex(index).fillna(0).to_numpy()
        if own_group is not None:
            by_group = ref.groupby([*keys, "_group"])["correct"].agg(["sum", "count"])
            lookup = pd.MultiIndex.from_arrays([*(rows[k] for k in keys), own_group])
            right = right - by_group["sum"].reindex(lookup).fillna(0).to_numpy()
            total = total - by_group["count"].reindex(lookup).fillna(0).to_numpy()
        return right, total

    sc, sn = counts(["skill_name"])
    ic, i_n = counts(["item_id"])
    skill = (sc + M_SKILL * base) / (sn + M_SKILL)
    item = (ic + M_ITEM * skill) / (i_n + M_ITEM)
    return logit(skill) - logit(base), logit(item) - logit(skill), item


def ridge_fit(x, y, w0, lam, weights=None):
    sw = np.ones(len(y)) if weights is None else weights

    def objective(w):
        z = x @ w
        loss = np.sum(sw * (np.logaddexp(0, z) - y * z)) + lam * np.sum((w - w0) ** 2)
        grad = x.T @ (sw * (sigmoid(z) - y)) + 2 * lam * (w - w0)
        return loss, grad

    return minimize(objective, w0, jac=True, method="L-BFGS-B").x


def design(causal, skill_effect, item_effect):
    return np.column_stack([causal, skill_effect, item_effect, np.ones(len(causal))])


def logloss(x, y, w):
    z = x @ w
    return float(np.sum(np.logaddexp(0, z) - y * z))


def choose_and_fit(x, y, group, w0):
    """Ridge strength by leave-one-group-out cross-validation; the candidate "never leave w0" is always included."""
    best, best_lam = sum(logloss(x[group == g], y[group == g], w0) for g in range(GROUPS)), None
    for lam in LAMBDAS:
        loss = 0.0
        for g in range(GROUPS):
            w = ridge_fit(x[group != g], y[group != g], w0, lam)
            loss += logloss(x[group == g], y[group == g], w)
        if loss < best:
            best, best_lam = loss, lam
    return (w0 if best_lam is None else ridge_fit(x, y, w0, best_lam)), best_lam


def dataset_matrix(data: pd.DataFrame, seed: int = 0):
    """Whole-dataset design matrix with out-of-group course features, used to learn transferable starting weights."""
    data = data.sort_values("order_id").reset_index(drop=True)
    causal, _ = causal_features(data)
    users = data["user_id"].unique()
    group_of = dict(zip(users, np.random.default_rng(seed).integers(0, GROUPS, len(users)), strict=True))
    group = data["user_id"].map(group_of).to_numpy()
    ref = data.assign(_group=group)
    skill_effect, item_effect, _ = course_features(data, ref, group)
    return design(causal, skill_effect, item_effect), data["correct"].to_numpy().astype(float)


def transfer_weights(others: list[pd.DataFrame]) -> np.ndarray:
    parts = [dataset_matrix(d) for d in others]
    x = np.vstack([p[0] for p in parts])
    y = np.concatenate([p[1] for p in parts])
    weights = np.concatenate([np.full(len(p[1]), 1 / len(p[1])) for p in parts]) * len(y) / len(parts)
    start = np.array([1.0, 0, 0, 0, 0, 0, 0])
    return ridge_fit(x, y, start, 1e-3, weights)


def auc_bootstrap(truth, predictions, user_rows, draws, rng):
    """95% interval for the AUC difference of two prediction vectors, resampling students."""
    keys = list(user_rows)
    out = []
    for _ in range(draws):
        picked = rng.integers(0, len(keys), len(keys))
        rows = np.concatenate([user_rows[keys[i]] for i in picked])
        if len(set(truth[rows])) < 2:
            continue
        out.append(roc_auc_score(truth[rows], predictions[0][rows]) - roc_auc_score(truth[rows], predictions[1][rows]))
    return np.percentile(out, [2.5, 97.5])


def evaluate(name: str, data: pd.DataFrame, w_transfer: np.ndarray, folds: int, draws: int) -> dict:
    data = data.sort_values("order_id").reset_index(drop=True)
    causal_all, lms_all = causal_features(data)
    print(f"{name}: {len(data)} answers, {data.user_id.nunique()} students, {data.skill_name.nunique()} skills, "
          f"{data.item_id.nunique()} items, {data.correct.mean():.3f} correct", flush=True)
    start = np.array([1.0, 0, 0, 0, 0, 0, 0])
    results: dict = {}
    stored: dict = {}
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=folds).split(data, groups=data["user_id"]), 1):
        train, test = data.iloc[tr].reset_index(drop=True), data.iloc[te].reset_index(drop=True)
        causal_tr, causal_te = causal_all[tr], causal_all[te]
        truth = test["correct"].to_numpy().astype(float)
        position = test.groupby("user_id").cumcount().to_numpy()
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
            ref = sub.assign(_group=group)
            skill_tr, item_tr, _ = course_features(sub, ref, group)
            skill_te, item_te, item_mean = course_features(test, sub)
            x_tr, x_te = design(causal_tr[mask], skill_tr, item_tr), design(causal_te, skill_te, item_te)
            base = (sub["correct"].sum() + M_GLOBAL * BASE0) / (len(sub) + M_GLOBAL)
            preds = {"lms_default": lms_all[te], "skill_mean": sigmoid(logit(base) + skill_te), "item_mean": item_mean}
            chosen_lambda = {}
            no_lms = w_transfer.copy()
            no_lms[0] = 0.0
            for label, w0, blank in (("stack_plain", start, False), ("stack_transfer", w_transfer, False),
                                     ("stack_no_lms", no_lms, True)):
                xa, xb = x_tr.copy(), x_te.copy()
                if blank:
                    xa[:, 0], xb[:, 0] = 0.0, 0.0
                if len(sub) >= 50 and level != 0:
                    w, chosen_lambda[label] = choose_and_fit(xa, y, group, w0)
                else:
                    w, chosen_lambda[label] = w0, None
                preds[label] = sigmoid(xb @ w)
            for label, p in preds.items():
                results.setdefault((level, label), []).append(metrics(truth, p))
            if level in (0, 30, 100, None):
                stored.setdefault(level, []).append((te, preds, position))
            print(f"fold {fold} N={'all' if level is None else level}: "
                  + ", ".join(f"{k} {results[(level, k)][-1]['AUC']:.4f}" for k in NAMES)
                  + f"  lambda {chosen_lambda}", flush=True)
    return {"results": results, "stored": stored, "data": data}


def metrics(truth, predicted):
    p = np.clip(predicted, 1e-6, 1 - 1e-6)
    bins = np.minimum((p * 10).astype(int), 9)
    ece = sum((bins == b).mean() * abs(p[bins == b].mean() - truth[bins == b].mean()) for b in range(10) if (bins == b).any())
    return {"AUC": roc_auc_score(truth, p), "Brier": float(np.mean((p - truth) ** 2)),
            "LogLoss": float(-np.mean(truth * np.log(p) + (1 - truth) * np.log(1 - p))), "ECE": float(ece)}


def report(name: str, run: dict, draws: int) -> None:
    results, stored, data = run["results"], run["stored"], run["data"]
    for metric in ("AUC", "ECE", "LogLoss"):
        print(f"\n### {name}: {metric} (mean over folds, std in brackets)\n")
        print("| Training students | " + " | ".join(NAMES) + " |\n| --- | " + " | ".join("---" for _ in NAMES) + " |")
        for level in LEVELS:
            if (level, NAMES[0]) not in results:
                continue
            cells = [f"{np.mean([r[metric] for r in results[(level, k)]]):.4f} "
                     f"({np.std([r[metric] for r in results[(level, k)]]):.4f})" for k in NAMES]
            print(f"| {'all' if level is None else level} | " + " | ".join(cells) + " |")
    truth = data["correct"].to_numpy().astype(float)
    users = data["user_id"].to_numpy()
    rng = np.random.default_rng(0)
    print(f"\n### {name}: AUC difference stack_transfer minus other model, 95% interval over students "
          f"({draws} resamples)\n\n| Training students | against | difference | interval |\n| --- | --- | --- | --- |")
    for level, parts in stored.items():
        merged = {k: np.zeros(len(data)) for k in NAMES}
        for te, preds, _ in parts:
            for k in NAMES:
                merged[k][te] = preds[k]
        user_rows = pd.Series(np.arange(len(users))).groupby(users).indices
        test_rows = np.arange(len(data))
        for other in ("lms_default", "item_mean", "stack_plain"):
            diff = roc_auc_score(truth[test_rows], merged["stack_transfer"][test_rows]) \
                - roc_auc_score(truth[test_rows], merged[other][test_rows])
            low, high = auc_bootstrap(truth, (merged["stack_transfer"], merged[other]), user_rows, draws, rng)
            print(f"| {'all' if level is None else level} | {other} | {diff:+.4f} | {low:+.4f} to {high:+.4f} |")
    print(f"\n### {name}: AUC by how many answers the student has already given (N = all training students)\n")
    print("| Earlier answers | Answers | lms_default | item_mean | stack_transfer |\n| --- | --- | --- | --- | --- |")
    parts = stored[None]
    pos = np.concatenate([p[2] for p in parts])
    truth_all = np.concatenate([truth[p[0]] for p in parts])
    for low, high in BUCKETS:
        chosen = (pos >= low) & (pos <= high)
        if chosen.sum() < 200 or len(set(truth_all[chosen])) < 2:
            continue
        cells = [f"{roc_auc_score(truth_all[chosen], np.concatenate([p[1][k] for p in parts])[chosen]):.4f}"
                 for k in ("lms_default", "item_mean", "stack_transfer")]
        print(f"| {low}{'+' if high > 10**8 else '' if low == high else f'-{high}'} | {chosen.sum()} | " + " | ".join(cells) + " |")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--bootstrap", type=int, default=100)
    parser.add_argument("--students", type=int, default=1500)
    parser.add_argument("--targets", default="assist09,ednet,csedm")
    args = parser.parse_args()
    loaders = {"assist09": load_assist09, "ednet": lambda: load_ednet(args.students), "csedm": load_csedm}
    datasets = {name: load() for name, load in loaders.items()}
    for name in args.targets.split(","):
        others = [d for k, d in datasets.items() if k != name]
        w = transfer_weights(others)
        print(f"\n## {name}: transferred starting weights (lms, student, n_on_skill, recent, skill, item, bias) = "
              f"{np.round(w, 3).tolist()}\n", flush=True)
        report(name, evaluate(name, datasets[name], w, args.folds, args.bootstrap), args.bootstrap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
