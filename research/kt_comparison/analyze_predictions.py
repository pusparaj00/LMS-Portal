"""Summarise saved test predictions (baselines_plus.py --save) over the folds that exist so far (TR-V-05).

For each training size it prints the mean AUC and ECE over the available folds, and the AUC difference of one model against the
others on the pooled test rows with a 95% interval from resampling test students. Only folds with the models being compared
are used, so a partly finished run can be read.

    python analyze_predictions.py DIR DATASET [--source assist09|ednet|csedm] [--focus hybrid] [--draws 200]
"""
import argparse
import glob
import os
import re

import numpy as np
import pandas as pd
from baselines_plus import auc_bootstrap
from cold_start_plus import load_csedm, metrics
from compare import load_assist09, load_ednet
from sklearn.metrics import roc_auc_score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("name", help="prefix of the saved files, for example assist09, ednet or csedm")
    parser.add_argument("--ednet-seed", type=int, default=0)
    parser.add_argument("--students", type=int, default=1500)
    parser.add_argument("--focus", default="hybrid")
    parser.add_argument("--draws", type=int, default=200)
    args = parser.parse_args()
    data = {"assist09": load_assist09, "ednet": lambda: load_ednet(args.students, args.ednet_seed), "csedm": load_csedm}[args.name]()
    data = data.sort_values("order_id").reset_index(drop=True)
    truth = data["correct"].to_numpy().astype(float)
    users = data["user_id"].to_numpy()
    files = sorted(glob.glob(os.path.join(args.directory, f"{args.name}_fold*_N*.npz")))
    by_level: dict[str, list] = {}
    for path in files:
        level = re.search(r"_N(\w+)\.npz$", path).group(1)
        by_level.setdefault(level, []).append(dict(np.load(path)))
    order = [x for x in ("30", "100", "300", "all") if x in by_level]
    for level in order:
        parts = by_level[level]
        models = [k for k in parts[0] if k != "rows"]
        models = [k for k in models if all(k in p for p in parts)]
        print(f"\n### {args.name}, N = {level}: {len(parts)} fold(s)\n")
        print("| Model | Mean AUC over folds | Mean ECE over folds |\n| --- | --- | --- |")
        for k in models:
            m = [metrics(truth[p["rows"]], p[k]) for p in parts]
            print(f"| {k} | {np.mean([x['AUC'] for x in m]):.4f} | {np.mean([x['ECE'] for x in m]):.4f} |")
        rows = np.concatenate([p["rows"] for p in parts])
        merged = {k: np.concatenate([p[k] for p in parts]) for k in models}
        sub_truth, sub_users = truth[rows], users[rows]
        user_rows = pd.Series(np.arange(len(rows))).groupby(sub_users).indices
        rng = np.random.default_rng(0)
        print(f"\nAUC of {args.focus} minus another model on the pooled rows of these folds, 95% interval over students\n")
        print("| Against | Difference | Interval |\n| --- | --- | --- |")
        for other in models:
            if other == args.focus or args.focus not in merged:
                continue
            diff = roc_auc_score(sub_truth, merged[args.focus]) - roc_auc_score(sub_truth, merged[other])
            low, high = auc_bootstrap(sub_truth, (merged[args.focus], merged[other]), user_rows, args.draws, rng)
            print(f"| {other} | {diff:+.4f} | {low:+.4f} to {high:+.4f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
