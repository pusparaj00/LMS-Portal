"""TR-M-15, TR-M-18: the pooled concept estimate (no database)."""
import numpy as np
import pytest

from app.diagnostic import pooled
from app.diagnostic.pooled import Answer, Question


def answer(concept, correct, a=1.0, b=0.0, slip=0.1, guess=0.25):
    return Answer({concept: 1.0}, a, b, slip, guess, correct)


def test_with_no_answers_every_concept_sits_at_the_prior():
    theta, covariance = pooled.fit([], 4)
    assert np.allclose(theta, 0.0)
    assert np.allclose(pooled.mastery(theta, covariance), pooled.mastery(theta, covariance)[0])
    assert pooled.mastery(theta, covariance)[0] == pytest.approx(0.5)


def test_right_answers_raise_and_wrong_answers_lower_the_concept():
    up = pooled.estimate([answer(0, True)], 3)
    down = pooled.estimate([answer(0, False)], 3)
    assert up[0] > 0.5 > down[0]


def test_an_answer_on_one_concept_moves_the_related_concepts_too():
    right = pooled.estimate([answer(0, True), answer(0, True)], 4, correlation=0.4)
    wrong = pooled.estimate([answer(0, False), answer(0, False)], 4, correlation=0.4)
    assert right[1] > 0.5 > wrong[1]  # concept 1 was never asked about
    independent = pooled.estimate([answer(0, True), answer(0, True)], 4, correlation=0.0)
    assert independent[1] == pytest.approx(0.5)  # without correlation the concepts do not share evidence
    assert right[0] > right[1] > 0.5  # the asked concept moves most


def test_more_answers_make_the_estimate_more_certain():
    one = pooled.fit([answer(0, True)], 3)
    three = pooled.fit([answer(0, True), answer(0, True), answer(0, False)], 3)
    assert np.diag(three[1])[0] < np.diag(one[1])[0]


def test_a_dont_know_counts_for_more_than_a_plain_wrong_answer():
    plain = pooled.estimate([answer(0, False)], 2)
    unknown = pooled.estimate([answer(0, False, guess=0.0)], 2)
    assert unknown[0] < plain[0]


def test_the_background_answer_moves_the_starting_point_only():
    assert pooled.estimate([], 2, prior_mean=-0.7)[0] < 0.5 < pooled.estimate([], 2, prior_mean=0.5)[0]
    many = [answer(0, True, b=0.5)] * 8
    assert pooled.estimate(many, 2, prior_mean=-0.7)[0] > 0.6  # the answers override the background


def test_the_expected_gain_is_larger_for_the_concept_with_less_evidence():
    answers = [answer(0, True), answer(0, False), answer(0, True), answer(1, True)]
    theta, covariance = pooled.fit(answers, 3)
    current = pooled.mastery(theta, covariance)
    gains = [pooled.expected_gain(Question({c: 1.0}, 1.0, 0.0, 0.1, 0.25), theta, covariance, current) for c in range(3)]
    assert gains[2] > gains[1] > gains[0]  # nothing asked about concept 2, one answer on 1, three on 0


def test_the_fit_is_stable_on_extreme_answer_patterns():
    answers = [answer(c % 3, True, a=2.0, b=-2.0) for c in range(30)] + [answer(0, False, a=2.0, b=3.0)] * 5
    theta, covariance = pooled.fit(answers, 3)
    assert np.all(np.isfinite(theta)) and np.all(np.isfinite(covariance))
    assert np.all((pooled.mastery(theta, covariance) > 0) & (pooled.mastery(theta, covariance) < 1))
