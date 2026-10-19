"""TR-M-03, TR-M-05, TR-M-10, TR-M-13: item selection and the ability estimate (no database)."""
import math

import pytest

from app.diagnostic import selection
from app.diagnostic.selection import Item


def mcq(item_id, concepts, b=0.0, a=1.0):
    return Item(item_id, "mcq", a, b, concepts)


def code(item_id, concepts, b=0.0, a=1.0):
    return Item(item_id, "code", a, b, concepts)


def bank():
    """14 tracing questions on 7 concepts, 8 coding tasks (4 of them hard), spread over the three bands."""
    items = [mcq(i, {i % 7: 1.0}, b=-1.2 + 0.2 * i) for i in range(14)]
    items += [code(100 + i, {i % 7: 1.0}, b=b) for i, b in enumerate((-1.0, -0.8, 0.0, 0.2, 0.8, 1.0, 1.2, 1.4))]
    return items


def run_test(items, seed, answer_right=True):
    asked: list[int] = []
    mastery = {c: 0.5 for i in items for c in i.concepts}
    for _ in range(selection.max_questions(items)):
        item = selection.select_next(items, asked, mastery, 0.0, seed)
        asked.append(item.id)
    return asked


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


def test_the_background_answer_moves_the_starting_point_and_the_answers_override_it():
    new, comfortable = (selection.BACKGROUND_PRIOR_MEAN[b] for b in ("new", "comfortable"))
    assert selection.eap_theta([], prior_mean=new) < 0 < selection.eap_theta([], prior_mean=comfortable)
    streak = [(1.0, 0.0, True, "mcq")] * 8
    assert selection.eap_theta(streak, prior_mean=new) > new + 1.0  # eight right answers beat a "new" background


def test_guessing_makes_a_correct_answer_weaker_evidence():
    # A four-option item is right 25% of the time by chance, so one correct answer says less than on a code task.
    assert selection.eap_theta([(1.0, 0.0, True, "mcq")]) < selection.eap_theta([(1.0, 0.0, True, "code")])


def test_a_wrong_answer_marked_dont_know_lowers_ability_more_than_a_plain_wrong_one():
    plain = selection.eap_theta([(1.0, 0.0, False, "diagnostic_mcq")])
    unknown = selection.eap_theta([(1.0, 0.0, False, "diagnostic_mcq_dontknow")])
    assert unknown < plain  # a student who knew the answer would not have said so, and there is no guess chance


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
    chosen = selection.select_next(items, [], {1: 0.95, 2: 0.5, 3: 0.05}, 0.0, "s")
    assert chosen.id == 2


def test_selection_prefers_questions_on_concepts_with_no_evidence_yet():
    items = [mcq(1, {1: 1.0}), mcq(2, {1: 1.0}), mcq(3, {2: 1.0})]
    assert selection.select_next(items, [1], {1: 0.5, 2: 0.5}, 0.0, "s").id == 3


def test_the_same_seed_gives_the_same_test_and_other_seeds_give_other_orders():
    items = bank()
    assert run_test(items, "a") == run_test(items, "a")
    orders = {tuple(run_test(items, f"seed{n}")) for n in range(8)}
    assert len(orders) >= 6  # students answering alike still meet different questions in a different order


def test_the_next_question_follows_the_ability_estimate():
    items = bank()
    easy = {selection.select_next(items, [], {c: 0.5 for c in range(7)}, -2.0, f"s{n}").b for n in range(10)}
    hard = {selection.select_next(items, [], {c: 0.5 for c in range(7)}, 2.0, f"s{n}").b for n in range(10)}
    assert max(easy) < min(hard)


def test_a_whole_test_keeps_to_the_type_limits_and_covers_every_concept_and_band():
    items = bank()
    by_id = {i.id: i for i in items}
    for n in range(10):
        asked = run_test(items, f"seed{n}")
        chosen = [by_id[a] for a in asked]
        assert len(asked) == len(set(asked)) == selection.MAX_ITEMS
        assert sum(i.kind == "mcq" for i in chosen) <= selection.MAX_MCQ
        assert sum(i.kind == "code" for i in chosen) <= selection.MAX_CODE
        assert sum(i.kind == "code" and selection.band(i.b) == "hard" for i in chosen) <= selection.MAX_HARD_CODE
        assert all(i.kind == "mcq" for i in chosen[: selection.WARMUP_ITEMS])
        assert not any(a.kind == b.kind == "code" for a, b in zip(chosen, chosen[1:], strict=False))
        assert selection.covered(items, asked) == set(range(7))
        assert {selection.band(i.b) for i in chosen} == {"easy", "medium", "hard"}


def test_a_course_with_only_coding_tasks_still_gets_a_test():
    items = [code(i, {i % 3: 1.0}, b=-1 + 0.3 * i) for i in range(10)]
    assert selection.max_questions(items) == selection.MAX_CODE
    asked: list[int] = []
    for _ in range(selection.max_questions(items)):
        asked.append(selection.select_next(items, asked, {0: 0.5, 1: 0.5, 2: 0.5}, 0.0, "s").id)
    assert len(set(asked)) == selection.MAX_CODE


def test_bands():
    assert [selection.band(b) for b in (-1.0, -0.5, 0.0, 0.5, 0.6)] == ["easy", "medium", "medium", "medium", "hard"]


def test_the_test_stops_early_only_when_every_concept_has_evidence_and_the_weakest_are_settled():
    items = bank()
    settled = {c: 0.98 for c in range(7)}
    unsettled = {c: 0.5 for c in range(7)}
    asked = run_test(items, "s")
    assert not selection.should_stop(items, asked[: selection.MIN_ITEMS - 1], settled)
    assert selection.should_stop(items, asked[: selection.MIN_ITEMS], settled)
    assert not selection.should_stop(items, asked[: selection.MIN_ITEMS], unsettled)
    assert selection.should_stop(items, asked, unsettled)  # the longest the course allows
    uncovered = [i for i in items if i.concepts.keys() != {6}][:20]
    assert not selection.should_stop(items, [i.id for i in uncovered][: selection.MIN_ITEMS], settled)


def test_probabilities_are_valid():
    for theta in (-4, 0, 4):
        assert 0 < selection.prob_correct(theta, 1.2, 0.3) < 1
        assert math.isfinite(selection.observed_probability(theta, 1.2, 0.3, "mcq"))
