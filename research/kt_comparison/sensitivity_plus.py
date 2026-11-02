"""Does the stack's advantage depend on the pseudo-count constants declared in cold_start_plus.py? (TR-V-05)

Each constant is halved and doubled, one at a time. For every setting the transfer weights are learned again on the other
datasets (so the features and the starting weights stay consistent) and the stack is evaluated against the default rule on
the target dataset at N = 0 and N = 100, 3 folds. Output: the AUC difference stack_transfer minus lms_default per setting.

    python sensitivity_plus.py [--targets assist09,ednet,csedm] [--folds 3]
"""
import argparse
import contextlib
import io

import cold_start_plus as csp
import numpy as np
from compare import load_assist09, load_ednet

CONSTANTS = ("M_STUDENT", "M_RECENT", "M_GLOBAL", "M_SKILL", "M_ITEM")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", default="assist09,ednet,csedm")
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--students", type=int, default=1500)
    args = parser.parse_args()
    datasets = {"assist09": load_assist09(), "ednet": load_ednet(args.students), "csedm": csp.load_csedm()}
    csp.LEVELS = [0, 100]
    declared = {name: getattr(csp, name) for name in CONSTANTS}
    settings = [("declared", None, 1.0)] + [(c, c, f) for c in CONSTANTS for f in (0.5, 2.0)]
    print("| Setting | " + " | ".join(f"{t} N=0 | {t} N=100" for t in args.targets.split(",")) + " |")
    print("| --- | " + " | ".join("--- | ---" for _ in args.targets.split(",")) + " |", flush=True)
    for label, constant, factor in settings:
        for name, value in declared.items():
            setattr(csp, name, value * (factor if name == constant else 1.0))
        cells = []
        for target in args.targets.split(","):
            w = csp.transfer_weights([d for k, d in datasets.items() if k != target])
            with contextlib.redirect_stdout(io.StringIO()):
                run = csp.evaluate(target, datasets[target], w, args.folds, 0)
            for level in (0, 100):
                gain = np.mean([r["AUC"] for r in run["results"][(level, "stack_transfer")]]) \
                    - np.mean([r["AUC"] for r in run["results"][(level, "lms_default")]])
                cells.append(f"{gain:+.4f}")
        name = "declared" if constant is None else f"{constant} x {factor:g} ({declared[constant] * factor:g})"
        print(f"| {name} | " + " | ".join(cells) + " |", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
