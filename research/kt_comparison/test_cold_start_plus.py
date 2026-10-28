"""Checks for the pieces of cold_start_plus.py, sequence_models.py and published_models.py that the claims rest on. Run in the research
environment (the sequence-model checks need PyTorch, so use the Python 3.12 environment for all of them):
    python test_cold_start_plus.py
"""
import numpy as np
import pandas as pd
from cold_start_plus import BASE0, causal_features, course_features, ridge_fit, sigmoid


def test_a_huge_ridge_keeps_the_prior_weights():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(500, 3))
    y = (rng.random(500) < sigmoid(x @ np.array([2.0, -1.0, 0.5]))).astype(float)
    w0 = np.array([1.0, 0.0, 0.0])
    assert np.allclose(ridge_fit(x, y, w0, 1e9), w0, atol=1e-4)


def test_a_tiny_ridge_recovers_the_generating_weights():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(20000, 3))
    true = np.array([2.0, -1.0, 0.5])
    y = (rng.random(20000) < sigmoid(x @ true)).astype(float)
    assert np.allclose(ridge_fit(x, y, np.zeros(3), 1e-6), true, atol=0.1)


def test_without_course_answers_the_course_features_are_neutral():
    rows = pd.DataFrame({"skill_name": ["a", "b"], "item_id": ["i", "j"], "correct": [1, 0]})
    skill, item, estimate = course_features(rows, rows.iloc[0:0])
    assert not skill.any() and not item.any() and np.allclose(estimate, BASE0)


def test_a_rows_own_group_is_left_out_of_its_counts():
    ref = pd.DataFrame({"skill_name": ["a"] * 4, "item_id": ["i"] * 4, "correct": [1, 1, 0, 0], "_group": [0, 0, 1, 1]})
    row = ref.iloc[[0]].reset_index(drop=True)
    with_own = course_features(row, ref)[2][0]
    without_own = course_features(row, ref, np.array([0]))[2][0]
    assert without_own < with_own  # group 0 holds the two right answers


def test_causal_features_use_only_earlier_answers():
    frame = pd.DataFrame({"user_id": ["u"] * 4, "skill_name": ["a"] * 4, "correct": [1, 1, 0, 1]})
    changed = frame.assign(correct=[1, 1, 1, 1])
    first, _ = causal_features(frame)
    second, _ = causal_features(changed)
    assert np.allclose(first[:3], second[:3])  # changing the third answer changes nothing up to and including itself
    assert not np.allclose(first[3], second[3])
    assert first[0, 2] == 0.0  # no earlier answers on the skill at the first answer


def test_every_test_row_is_scored_exactly_once_by_the_sequence_windows():
    from sequence_models import WINDOW, windows

    lengths = [3, WINDOW, WINDOW + 1, 3 * WINDOW + 7]
    frame = pd.concat([pd.DataFrame({"user_id": f"u{i}", "skill_name": "a", "item_id": "x", "correct": 1}, index=range(n))
                       for i, n in enumerate(lengths)], ignore_index=True)
    w = windows(frame, {"a": 1}, {"x": 1}, training=False)
    rows = w["row"][w["scored"]].numpy()
    assert sorted(rows) == list(range(len(frame)))


def test_a_sequence_prediction_does_not_depend_on_later_answers():
    import torch
    from sequence_models import WINDOW, Net

    torch.manual_seed(0)
    net = Net(3, 4, "akt_lite").eval()
    skill = torch.randint(1, 4, (1, WINDOW))
    item = torch.randint(1, 5, (1, WINDOW))
    correct = torch.randint(0, 2, (1, WINDOW))
    changed = correct.clone()
    changed[0, 40] = 1 - changed[0, 40]
    with torch.no_grad():
        before, after = net(skill, item, correct), net(skill, item, changed)
    assert torch.allclose(before[0, :41], after[0, :41], atol=1e-5)  # up to and including position 40
    assert not torch.allclose(before[0, 41:], after[0, 41:], atol=1e-5)


def test_the_published_models_do_not_depend_on_later_answers():
    import torch
    from published_models import build, probabilities
    from sequence_models import WINDOW

    torch.manual_seed(0)
    for kind in ("dkt", "akt"):
        net = build(kind, 3, 4).eval()
        w = {"skill": torch.randint(1, 4, (1, WINDOW)), "item": torch.randint(1, 5, (1, WINDOW)),
             "correct": torch.randint(0, 2, (1, WINDOW))}
        changed = {k: v.clone() for k, v in w.items()}
        changed["correct"][0, 40] = 1 - changed["correct"][0, 40]
        with torch.no_grad():
            before, after = (torch.nan_to_num(probabilities(net, kind, x)[0], nan=-1) for x in (w, changed))
        assert torch.allclose(before[0, :41], after[0, :41], atol=1e-5), kind  # up to and including position 40
        assert not torch.allclose(before[0, 41:], after[0, 41:], atol=1e-5), kind


if __name__ == "__main__":
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            print("ok", name)
