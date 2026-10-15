"""TR-M-03, TR-M-05, TR-M-10: item selection and the ability estimate (no database)."""
import math

import pytest

from app.diagnostic import selection
from app.diagnostic.selection import Item


def mcq(item_id, concepts, b=0.0, a=1.0):
    return Item(item_id, "mcq", a, b, concepts)


def test_fisher_information_peaks_where_difficulty_equals_ability():
    at_peak = selection.fisher_information(0.5, 1.5, 0.5)
    assert at_peak == pytest.approx(1.5**2 / 4)
    assert at_peak > selection.fisher_information(2.0, 1.5, 0.5)
    assert at_peak > selection.fisher_information(-1.0, 1.5, 0.5)


def test_the_ability_prior_keeps_short_tests_off_the_bounds():
    one_right = selection.eap_theta([(1.0, 0.0, True, "mcq")])
    all_right = selection.eap_theta([(1.0, 0.0, True, "mcq")] * 5)
    assert 0 < one_right < 1.0  # a single answer does not snap to the clip bound
    assert one_right < all_right < 4.0
    assert selection.eap_theta([]) == pytest.approx(0.0, abs=1e-9)


def test_guessing_makes_a_correct_answer_weaker_evidence():
    # A four-option item is right 25% of the time by chance, so one correct answer says less than on a code task.
    assert selection.eap_theta([(1.0, 0.0, True, "mcq")]) < selection.eap_theta([(1.0, 0.0, True, "code")])


def test_entropy_is_highest_at_one_half():
    assert selection.entropy(0.5) == pytest.approx(1.0)
    assert selection.entropy(0.99) < selection.entropy(0.7) < selection.entropy(0.5)


def test_information_gain_is_larger_for_uncertain_concepts():
    item_a, item_b = mcq(1, {1: 1.0}), mcq(2, {2: 1.0})
    mastery = {1: 0.5, 2: 0.97}
    assert selection.expected_information_gain(item_a, mastery, 0.0) > selection.expected_information_gain(
        item_b, mastery, 0.0
    )


def test_selection_prefers_the_item_on_the_most_uncertain_concept():
    items = [mcq(1, {1: 1.0}), mcq(2, {2: 1.0}), mcq(3, {3: 1.0})]
    chosen = selection.select_next(items, set(), {1: 0.95, 2: 0.5, 3: 0.05}, 0.0)
    assert chosen.id == 2


def test_selection_is_deterministic_and_skips_asked_items():
    items = [mcq(i, {1: 1.0}) for i in range(1, 5)]
    first = selection.select_next(items, set(), {1: 0.5}, 0.0)
    assert first == selection.select_next(items, set(), {1: 0.5}, 0.0)
    assert selection.select_next(items, {first.id}, {1: 0.5}, 0.0).id != first.id
    assert selection.select_next(items, {1, 2, 3, 4}, {1: 0.5}, 0.0) is None


def test_the_test_is_tracing_items_then_two_short_coding_tasks():
    items = [mcq(i, {1: 1.0}) for i in range(10)] + [
        Item(100, "code", 1.0, 0.0, {1: 1.0}),
        Item(101, "code", 1.0, 1.5, {1: 1.0}),  # too hard to count as short
        Item(102, "code", 1.0, -0.5, {1: 1.0}),
    ]
    asked: set[int] = set()
    kinds = []
    for _ in range(selection.MAX_ITEMS):
        item = selection.select_next(items, asked, {1: 0.5}, 0.0)
        kinds.append(item.kind)
        asked.add(item.id)
    assert kinds == ["mcq"] * 8 + ["code"] * 2
    assert 101 not in asked


def test_the_test_stops_at_the_maximum_or_when_concepts_are_settled():
    assert selection.finished(selection.MAX_ITEMS, {1: 0.5})
    assert not selection.finished(5, {1: 0.5})
    settled = {c: 0.98 for c in range(12)}
    assert not selection.finished(selection.MIN_ITEMS_BEFORE_STOP - 1, settled)
    assert selection.finished(selection.MIN_ITEMS_BEFORE_STOP, settled)


def test_probabilities_are_valid():
    for theta in (-4, 0, 4):
        assert 0 < selection.prob_correct(theta, 1.2, 0.3) < 1
        assert math.isfinite(selection.observed_probability(theta, 1.2, 0.3, "mcq"))
