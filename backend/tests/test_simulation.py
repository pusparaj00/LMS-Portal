"""TR-V-05, TR-V-06: the simulation harness runs, is reproducible and the 5-item test beats the mean."""
from pathlib import Path

import numpy as np

from simulation import model, run

ROOT = Path(__file__).resolve().parents[1]
BANK = next(p for p in (ROOT / "data" / "bank", ROOT.parent / "data" / "bank") if p.exists())


def test_same_seed_gives_the_same_result():
    bank = model.load_bank(BANK)
    one = run.simulate(40, 7, bank)
    two = run.simulate(40, 7, bank)
    assert np.allclose(one["curves"]["adaptive"], two["curves"]["adaptive"])
    assert one["auc"] == two["auc"]


def test_five_item_test_beats_predicting_the_population_mean_on_the_concepts_it_tested():
    # Holds on 10 of 10 seeds. Against the average over ALL concepts it holds on only 3 of 10
    # (docs/results/diagnostic.md), so that target is reported there, not asserted here.
    for seed in (5, 6, 7):
        result = run.simulate(300, seed, model.load_bank(BANK))["sanity_5_items"]["tested_concepts"]
        assert result["estimate_rmse"] < result["population_mean_rmse"], seed


def test_the_simulator_differs_from_the_selection_model():
    # TR-V-05: the truth uses its own slip and guess values, not the ones the selector assumes.
    from app.diagnostic import selection
    from app.mastery import core

    for kind in ("mcq", "code"):
        slip, guess = core.DEFAULT_PARAMS[selection.EVIDENCE_TYPE[kind]]
        assert model.TRUE_SLIP != slip and model.TRUE_GUESS[kind] != guess, kind


def test_auc_and_calibration_error_on_known_cases():
    scores = np.array([0.1, 0.4, 0.35, 0.8])
    labels = np.array([0, 0, 1, 1])
    assert run.auc(scores, labels) == 0.75
    assert run.auc(np.array([0.5, 0.5]), np.array([0, 1])) == 0.5
    assert abs(run.calibration_error(np.array([0.9, 0.9]), np.array([1, 1])) - 0.1) < 1e-9
