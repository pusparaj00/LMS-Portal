"""TR-M-01, TR-M-07, TR-M-09: the update rule, evidence weighting and replay (no database)."""
import pytest

from app.mastery import core
from app.mastery.plan import Plan, plan_submission


def test_correct_answer_raises_and_wrong_answer_lowers_mastery():
    assert core.bayes_update(0.5, 0.1, 0.2, True) > 0.5
    assert core.bayes_update(0.5, 0.1, 0.2, False) < 0.5


def test_update_matches_the_drd_formula():
    p, s, g = 0.4, 0.1, 0.2
    assert core.bayes_update(p, s, g, True) == pytest.approx(p * (1 - s) / (p * (1 - s) + (1 - p) * g))
    assert core.bayes_update(p, s, g, False) == pytest.approx(p * s / (p * s + (1 - p) * (1 - g)))


@pytest.mark.parametrize("p", [0.0, 1e-9, 0.3, 0.999999, 1.0])
@pytest.mark.parametrize("correct", [True, False])
def test_mastery_always_stays_between_zero_and_one(p, correct):
    for _ in range(50):
        p = core.weighted_update(p, 0.1, 0.2, correct, 1.0)
    assert 0.0 < p < 1.0


def test_partial_failure_lowers_mastery_less_than_total_failure():
    partial = core.bayes_update(0.6, *core.DEFAULT_PARAMS["partial_fail"], False)
    total = core.bayes_update(0.6, *core.DEFAULT_PARAMS["full_fail"], False)
    assert total < partial < 0.6


def test_weight_scales_the_size_of_the_update():
    full = core.weighted_update(0.5, 0.1, 0.2, True, 1.0) - 0.5
    half = core.weighted_update(0.5, 0.1, 0.2, True, 0.5) - 0.5
    assert half == pytest.approx(full / 2)
    assert core.weighted_update(0.5, 0.1, 0.2, True, 0.0) == 0.5


def test_default_rates_satisfy_slip_plus_guess_below_one():
    assert all(s + g < 1 for s, g in core.DEFAULT_PARAMS.values())


def test_misconception_probability_rises_on_its_option_and_falls_on_the_correct_answer():
    raised = core.misconception_update(0.1, picked_its_option=True, chose_correct=False)
    lowered = core.misconception_update(0.5, picked_its_option=False, chose_correct=True)
    assert raised > 0.1 and lowered < 0.5
    assert core.misconception_update(0.3, picked_its_option=False, chose_correct=False) == 0.3


def test_propagation_only_for_sharp_drops():
    assert core.propagated(0.5, 0.60, 0.55) is None
    lowered = core.propagated(0.5, 0.8, 0.4)
    assert lowered == pytest.approx(0.5 - core.PROPAGATION_FRACTION * 0.4)


def test_replaying_the_ledger_gives_the_same_vector_every_time():
    params = {(1, "all_pass"): (0.1, 0.2), (1, "full_fail"): (0.1, 0.2), (2, "full_fail"): (0.1, 0.2)}
    priors = {1: 0.5, 2: 0.5}
    p = priors[1]
    events = []
    for n, (evidence, ok) in enumerate([("all_pass", True), ("full_fail", False), ("full_fail", False)], 1):
        after = core.weighted_update(p, 0.1, 0.2, ok, 0.8)
        events.append(core.Event(n, 1, "bayes_update", evidence, 0.8, ok, p, after, None))
        p = after
    first = core.replay(priors, events, params)
    assert first == core.replay(priors, events, params)
    assert first[1] == pytest.approx(p) and first.get(2, priors[2]) == priors[2]


def test_replay_applies_propagation_from_the_source_event():
    params = {(1, "full_fail"): (0.1, 0.2)}
    priors = {1: 0.5, 2: 0.5}
    drop = core.weighted_update(0.5, 0.1, 0.2, False, 1.0)
    events = [
        core.Event(1, 1, "bayes_update", "full_fail", 1.0, False, 0.5, drop, None),
        core.Event(2, 2, "prerequisite_propagation", "propagation", 0.3, None, 0.5, 0.0, 1),
    ]
    result = core.replay(priors, events, params)
    assert result[2] == pytest.approx(core.propagated(0.5, 0.5, drop))


PROBLEM = {10: 0.8, 11: 0.2}
MAP = [("invalid_token", "*", 10, 1.0), ("*", "syntax_error", 11, 1.0), ("*", "time_limit", 12, 1.0)]


def plan(**overrides):
    base = dict(status="failed", passed=1, error_type=None, failed_categories=[],
                problem_concepts=PROBLEM, map_rows=MAP)
    return plan_submission(**{**base, **overrides})


def test_all_tests_passing_strengthens_every_tagged_concept():
    assert plan(status="passed", passed=5) == {10: Plan("all_pass", 0.8, True), 11: Plan("all_pass", 0.2, True)}


def test_a_failed_category_changes_only_its_linked_concepts():
    result = plan(failed_categories=["invalid_token"])
    assert set(result) == {10}
    assert result[10] == Plan("partial_fail", 0.8, False)


def test_an_unmapped_category_falls_back_to_the_problems_concepts():
    assert set(plan(failed_categories=["zero"])) == {10, 11}


def test_a_total_failure_is_stronger_evidence_than_a_partial_one():
    assert plan(passed=0, failed_categories=["zero"])[10].evidence_type == "full_fail"


def test_a_syntax_error_touches_only_the_syntax_concept():
    assert plan(status="error", error_type="syntax_error", passed=0, failed_categories=["x"]) == {
        11: Plan("syntax_error", 0.2, False)
    }


def test_a_timeout_goes_to_the_mapped_concept_and_replaces_the_wrong_answer_evidence():
    result = plan(error_type="time_limit", failed_categories=["zero"])
    assert result[12] == Plan("time_limit", 1.0, False)
    assert result[10].evidence_type == "partial_fail"


def test_answer_rules_pick_the_evidence_type_and_keep_the_rates_valid():
    assert core.answer_evidence_type("diagnostic_mcq") == "diagnostic_mcq"
    assert core.answer_evidence_type("diagnostic_mcq", confidence="fairly") == "diagnostic_mcq"
    assert core.answer_evidence_type("diagnostic_mcq", confidence="guessing") == "diagnostic_mcq_guess"
    assert core.answer_evidence_type("diagnostic_mcq", confidence="sure") == "diagnostic_mcq_sure"
    assert core.answer_evidence_type("diagnostic_code", confidence="sure") == "diagnostic_code"
    assert core.answer_evidence_type("diagnostic_code", dont_know=True) == "diagnostic_code_dontknow"
    assert core.answer_evidence_type("diagnostic_mcq", dont_know=True, confidence="sure") == "diagnostic_mcq_dontknow"


def test_confidence_and_dont_know_change_how_much_an_answer_is_worth():
    def after(evidence, correct):
        return core.weighted_update(0.5, *core.DEFAULT_PARAMS[evidence], correct, 1.0)

    assert after("diagnostic_mcq_guess", True) < after("diagnostic_mcq", True) < after("diagnostic_mcq_sure", True)
    assert after("diagnostic_mcq_sure", False) < after("diagnostic_mcq", False) < after("diagnostic_mcq_guess", False)
    assert after("diagnostic_mcq_dontknow", False) < after("diagnostic_mcq", False)


def test_an_inferred_value_follows_ability_and_stays_near_one_half():
    low, middle, high = (core.inferred_target(t, 0.0) for t in (-3.0, 0.0, 3.0))
    assert low < middle == 0.5 < high
    assert 0.05 <= low and high <= 0.95
    assert core.inferred_target(0.0, 2.0) < core.inferred_target(0.0, -2.0)  # harder concepts get a lower value
    moved = core.inferred_update(0.5, high)
    assert 0.5 < moved < high  # a low weight: it moves part of the way, never all of it


def test_replay_applies_an_ability_inference_row():
    priors = {1: 0.5}
    event = core.Event(1, 1, core.RULE_INFERENCE, "diagnostic_inferred", core.INFERENCE_WEIGHT, None, 0.5, 0.58, None, 0.77)
    assert core.replay(priors, [event], {})[1] == pytest.approx(core.inferred_update(0.5, 0.77))


def test_confidence_grows_with_the_amount_of_real_evidence():
    labels = [core.confidence_label(n) for n in (0.3, 1.0, 3.0, 8.0)]
    assert labels == ["low", "low", "moderate", "higher"]
    assert core.uncertainty(0) > core.uncertainty(4) > core.uncertainty(20)
