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


def test_five_question_pooled_estimate_beats_predicting_the_population_mean():
    # The average mastery after 5 questions against the true average mastery (TR-V-06), on three seeds.
    for seed in (5, 6, 7):
        sanity = run.simulate(150, seed, model.load_bank(BANK))["sanity_5_items"]
        for key in ("pooled_all", "pooled_tested"):
            assert sanity[key]["estimate_rmse"] < sanity[key]["population_mean_rmse"], (seed, key)


def test_the_pooled_estimate_is_closer_to_the_truth_than_the_independent_one():
    result = run.simulate(150, 11, model.load_bank(BANK))["curves"]
    assert result["adaptive_pooled"][-1] < result["adaptive"][-1]
    assert result["random_pooled"][-1] < result["random"][-1]


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


def test_a_strong_student_ends_above_a_weak_one_on_every_seed():
    # Gate of step 54: same course, same bank, only the answers differ.
    bank = model.load_bank(BANK)
    n = len(bank.items)
    for seed in range(10):
        ends = {}
        for name, answers in (("strong", np.ones(n)), ("weak", np.zeros(n))):
            rng = np.random.default_rng(seed)
            truth = np.full(len(bank.concepts), 0.5)
            _, _, abilities, _ = run.run_student("adaptive", bank.items, answers, truth, rng, len(bank.concepts), f"s{seed}")
            ends[name] = abilities[-1]
        assert ends["strong"] > 1.0 > -1.0 > ends["weak"], (seed, ends)


def test_the_textbook_adaptive_test_picks_the_item_with_the_most_information_at_the_ability():
    from app.diagnostic import selection

    near = selection.Item(1, "mcq", a=1.0, b=0.0, concepts={0: 1.0})
    far = selection.Item(2, "mcq", a=1.0, b=3.0, concepts={0: 1.0})
    sharp = selection.Item(3, "mcq", a=2.0, b=0.2, concepts={0: 1.0})
    assert run.most_informative([far, near, sharp], 0.0).id == 3
    assert run.most_informative([far, near], 0.0).id == 1
    assert run.most_informative([far, near], 3.0).id == 2
    assert run.most_informative([near, selection.Item(4, "mcq", a=1.0, b=0.0, concepts={0: 1.0})], 0.0).id == 1


def test_the_new_baselines_ask_the_full_allowed_test_without_repeats_and_fixed_order_is_by_id():
    bank = model.load_bank(BANK)
    answers = np.ones(len(bank.items))
    truth = np.full(len(bank.concepts), 0.5)
    from app.diagnostic import selection

    length = selection.max_questions(bank.items)
    for policy in ("cat_info", "fixed"):
        rng = np.random.default_rng(1)
        errors, _, _, asked = run.run_student(policy, bank.items, answers, truth, rng, len(bank.concepts), "s")
        assert len(asked) == length and len(set(asked)) == length and len(errors) == length
    _, _, _, asked = run.run_student("fixed", bank.items, answers, truth, np.random.default_rng(1), len(bank.concepts), "s")
    tracing = [i for i in asked if bank.items[i].kind == "mcq"]
    assert tracing == sorted(tracing)


def test_every_policy_appears_in_the_simulated_curves_and_the_report():
    bank = model.load_bank(BANK)
    result = run.simulate(20, 3, bank)
    assert {"cat_info", "fixed", "cat_info_pooled", "fixed_pooled"} <= set(result["curves"])
    # their answers can overlap the held-out items, so they are not scored on held-out responses
    assert not {"cat_info", "fixed"} & set(result["auc"])
    import argparse

    args = argparse.Namespace(students=20, seed=3, items=bank.items, prior_flags="")
    text = run.report(result, args)
    assert "max-information adaptive" in text and "fixed order" in text and "Items needed to reach" in text
