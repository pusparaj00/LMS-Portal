"""TR-M-03, TR-M-05, TR-M-10, TR-M-13: choice of the next question and the stop rule (no database)."""
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


def run_test(items, seed, right=True):
    given: list[selection.Response] = []
    for _ in range(selection.max_questions(items)):
        item = selection.select_next(items, given, seed)
        given.append((item.id, right, selection.EVIDENCE_TYPE[item.kind]))
    return given


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


def test_selection_prefers_questions_on_concepts_with_no_evidence_yet():
    items = [mcq(1, {1: 1.0}), mcq(2, {1: 1.0}), mcq(3, {2: 1.0}), mcq(4, {1: 1.0})]
    assert selection.select_next(items, [(4, True, "diagnostic_mcq")], "s").id == 3


def test_the_same_seed_gives_the_same_test_and_other_seeds_give_other_orders():
    items = bank()
    assert run_test(items, "a") == run_test(items, "a")
    orders = {tuple(i for i, _, _ in run_test(items, f"seed{n}")) for n in range(8)}
    assert len(orders) >= 6  # students answering alike still meet different questions in a different order


def test_the_next_question_follows_the_answers():
    items = bank()

    def mean_difficulty(right):
        asked = [(i, right, "diagnostic_mcq") for i in (3, 5, 7, 9)]
        chosen = [selection.select_next(items, asked, f"s{n}") for n in range(12)]
        return sum(i.b for i in chosen) / len(chosen)

    assert mean_difficulty(True) > mean_difficulty(False) + 0.3  # right answers move the test up, wrong ones down


def test_a_whole_test_keeps_to_the_type_limits_and_covers_every_concept_and_band():
    items = bank()
    by_id = {i.id: i for i in items}
    for n in range(10):
        asked = [i for i, _, _ in run_test(items, f"seed{n}")]
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
    given: list[selection.Response] = []
    for _ in range(selection.max_questions(items)):
        given.append((selection.select_next(items, given, "s").id, True, "diagnostic_code"))
    assert len({i for i, _, _ in given}) == selection.MAX_CODE


def test_bands():
    assert [selection.band(b) for b in (-1.0, -0.5, 0.0, 0.5, 0.6)] == ["easy", "medium", "medium", "medium", "hard"]


def test_the_test_runs_to_the_longest_length_the_course_allows():
    items = bank()
    given = run_test(items, "s")
    assert not selection.should_stop(items, given[:-1])
    assert selection.should_stop(items, given)
    assert len(given) == selection.max_questions(items) == selection.MAX_ITEMS


def test_probabilities_are_valid():
    for theta in (-4, 0, 4):
        assert 0 < selection.prob_correct(theta, 1.2, 0.3) < 1
        assert math.isfinite(selection.observed_probability(theta, 1.2, 0.3, "mcq"))


def test_the_learner_record_tells_assessed_estimated_and_not_assessed_apart():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.routers.diagnostic import _learner_record

    def row(n, n_eff, inferred):
        last = datetime(2026, 10, 19, tzinfo=UTC) if n else None
        return SimpleNamespace(id=1, name="loops", p=0.6, n=n, n_eff=n_eff, last=last, inferred=inferred)

    assessed = _learner_record(row(4, 3.5, None))
    estimated = _learner_record(row(None, None, True))
    none = _learner_record(row(None, None, None))
    assert (assessed.status, assessed.evidence_count, assessed.confidence) == ("assessed", 4, "moderate")
    assert assessed.last_assessed.startswith("2026-10-19")
    assert (estimated.status, estimated.evidence_count, estimated.confidence) == ("estimated", 0, None)
    assert (none.status, none.confidence, none.last_assessed) == ("not assessed", None, None)


def test_a_tracing_questions_guess_rate_is_one_over_its_options():
    assert selection.slip_guess("diagnostic_mcq", 3) == (0.1, pytest.approx(1 / 3))
    assert selection.slip_guess("diagnostic_mcq", 4) == (0.1, pytest.approx(0.25))
    assert selection.slip_guess("diagnostic_mcq", None) == selection.slip_guess("diagnostic_mcq")


def test_the_confidence_variants_and_coding_tasks_keep_their_declared_guess_rates():
    for evidence in ("diagnostic_mcq_guess", "diagnostic_mcq_dontknow", "diagnostic_code"):
        assert selection.slip_guess(evidence, 3) == selection.slip_guess(evidence, None)


def test_a_right_answer_to_a_three_option_question_is_weaker_evidence_than_to_a_four_option_one():
    def estimate(options):
        items = [Item(i, "mcq", 1.0, 0.0, {0: 1.0}, options) for i in range(3)]
        given = [(i, True, "diagnostic_mcq") for i in range(3)]
        _, theta, _ = selection.posterior(items, given)
        return float(theta[0])

    assert estimate(3) < estimate(4)


def test_the_option_chance_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(selection, "USE_OPTION_CHANCE", False)
    assert selection.slip_guess("diagnostic_mcq", 3) == selection.slip_guess("diagnostic_mcq")


def test_the_cover_weight_is_a_declared_positive_constant():
    assert 0 < selection.COVER_WEIGHT <= 1.5
