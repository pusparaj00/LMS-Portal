"""Checks for the pieces of cold_start_plus.py that the claims rest on. Run in the research environment:
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


if __name__ == "__main__":
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            print("ok", name)
