"""Tuned versions of the baselines (TR-V-05), so that the stack is compared with models that had a search as large as its own.

Budget, declared before any tuned run: every tuned model gets the same number of candidate settings (BUDGET = 6). The
setting is chosen by log-loss on a held-out fifth of the N training students (chosen by student, fixed seed); the model
is then refitted on all N students. Test students are never used to choose anything.

  gbdt_tuned   HistGradientBoosting on the stack's six features: learning rate, depth, L2 and iterations
  pfa_tuned    PFA: C over six values (the default PFA picks among three)
  rasch_tuned  Rasch with online ability: C over six values (the default Rasch uses C = 1)
  <neural>_tuned  SAKT, SAKT+item, AKT-lite, DKT and AKT: six (learning rate, width, dropout) settings; the one with the lowest
                  loss on the held-out fifth is kept (the default setting is one of the six)
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

BUDGET = 6
GBDT_SETTINGS = [
    {"learning_rate": 0.1, "max_depth": None, "l2_regularization": 0.0, "max_iter": 200},
    {"learning_rate": 0.05, "max_depth": 3, "l2_regularization": 1.0, "max_iter": 300},
    {"learning_rate": 0.05, "max_depth": 5, "l2_regularization": 1.0, "max_iter": 300},
    {"learning_rate": 0.03, "max_depth": 3, "l2_regularization": 10.0, "max_iter": 400},
    {"learning_rate": 0.1, "max_depth": 2, "l2_regularization": 0.0, "max_iter": 200},
    {"learning_rate": 0.02, "max_depth": 4, "l2_regularization": 5.0, "max_iter": 500},
]
PFA_C_TUNED = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
RASCH_C_TUNED = [0.1, 0.3, 1.0, 3.0, 10.0, 30.0]
# Neural models: learning rate, width and dropout. Widths divide the attention heads (2 for the SAKT family, 8 for AKT).
SEQUENCE_SETTINGS = [
    {"lr": 2e-3, "dim": 48, "dropout": 0.2},
    {"lr": 1e-3, "dim": 48, "dropout": 0.1},
    {"lr": 5e-3, "dim": 32, "dropout": 0.2},
    {"lr": 2e-3, "dim": 64, "dropout": 0.3},
    {"lr": 1e-3, "dim": 64, "dropout": 0.2},
    {"lr": 5e-3, "dim": 48, "dropout": 0.3},
]
PUBLISHED_SETTINGS = [
    {"lr": 1e-3, "dim": 128},
    {"lr": 5e-4, "dim": 128, "dropout": 0.3},
    {"lr": 2e-3, "dim": 64, "dropout": 0.1},
    {"lr": 1e-3, "dim": 64, "dropout": 0.3},
    {"lr": 5e-4, "dim": 256, "dropout": 0.2},
    {"lr": 2e-3, "dim": 128, "dropout": 0.2},
]
assert len(SEQUENCE_SETTINGS) == len(PUBLISHED_SETTINGS) == BUDGET
assert len(GBDT_SETTINGS) == len(PFA_C_TUNED) == len(RASCH_C_TUNED) == BUDGET


def held_out_students(users: np.ndarray) -> np.ndarray:
    """Boolean mask over rows: the fifth of the training students kept back to choose a setting."""
    ids = np.unique(users)
    held = np.random.default_rng(0).choice(ids, size=max(1, len(ids) // 5), replace=False)
    return np.isin(users, held)


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def tuned_gbdt(x: np.ndarray, y: np.ndarray, users: np.ndarray) -> HistGradientBoostingClassifier:
    """x holds the stack's six features in its first six columns. Falls back to the first setting when a side is empty."""
    held = held_out_students(users)

    def make(setting: dict) -> HistGradientBoostingClassifier:
        return HistGradientBoostingClassifier(early_stopping=False, random_state=0, **setting)

    best = GBDT_SETTINGS[0]
    if held.any() and not held.all() and len(np.unique(y[~held])) == 2:
        best = min(GBDT_SETTINGS, key=lambda s: log_loss(y[held], make(s).fit(x[~held], y[~held]).predict_proba(x[held])[:, 1]))
    return make(best).fit(x, y)


def tuned_rasch_c(sub: pd.DataFrame, rasch_predict) -> float:
    held = held_out_students(sub["user_id"].to_numpy())
    if not held.any() or held.all():
        return 1.0
    train, check = sub[~held].reset_index(drop=True), sub[held].reset_index(drop=True)
    truth = check["correct"].to_numpy().astype(float)
    return min(RASCH_C_TUNED, key=lambda c: log_loss(truth, rasch_predict(train, check, c)))
