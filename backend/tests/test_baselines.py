"""TR-L-04, TR-V-03: the baseline harness resamples whole failures, counts ablations correctly and reports no-reply cases."""
import numpy as np

from evaluation import baselines


def rec(case, **flags):
    return {"case": case, "flow": "verified", "replied": True} | flags


def test_a_share_with_no_replies_is_reported_as_missing_not_zero():
    assert baselines.share_interval([], "shows_solution", np.random.default_rng(0)) is None
    assert baselines.format_share(None) == "no replies"


def test_the_share_and_its_interval_follow_the_data():
    records = [rec(i, flag=i < 6) for i in range(10)]
    point, low, high, total = baselines.share_interval(records, "flag", np.random.default_rng(0))
    assert point == 0.6 and total == 10
    assert 0.2 < low < 0.6 < high < 1.0


def test_repeats_of_one_failure_do_not_narrow_the_interval():
    once = [rec(i, flag=i < 3) for i in range(6)]
    repeated = [rec(i, flag=i < 3) for i in range(6) for _ in range(5)]
    rng = np.random.default_rng(1)
    _, low1, high1, _ = baselines.share_interval(once, "flag", rng)
    _, low2, high2, n = baselines.share_interval(repeated, "flag", np.random.default_rng(1))
    assert n == 30
    assert abs((high2 - low2) - (high1 - low1)) < 0.12  # the same six failures carry the same uncertainty


def test_all_or_nothing_data_has_a_degenerate_interval():
    point, low, high, _ = baselines.share_interval([rec(i, flag=True) for i in range(5)], "flag", np.random.default_rng(0))
    assert (point, low, high) == (1.0, 1.0, 1.0)


def test_ablation_counts_what_each_check_rejected_and_what_it_rejected_alone():
    records = [
        rec(1, failed=["no_hidden_test_leak"]), rec(2, failed=["no_hidden_test_leak", "claim_length"]),
        rec(3, failed=[]), rec(4, failed=["json_valid"]), rec(5, failed=["no_hidden_test_leak"]),
    ]
    rows = {name: (rejected, alone) for name, rejected, alone in baselines.ablation(records)}
    assert rows == {"no_hidden_test_leak": (3, 2), "claim_length": (1, 0), "json_valid": (1, 1)}
    assert baselines.ablation(records)[0][0] == "no_hidden_test_leak"


def test_the_formatted_share_shows_the_interval_and_the_number_of_replies():
    assert baselines.format_share((0.5, 0.25, 0.75, 12)) == "50% (25% to 75%), 12 replies"
