"""Cold-start diagnostic maths (TR-M-03, TR-M-05, TR-M-10).

The 2PL probability, Fisher information and prior-regularised ability estimate follow the formulas
in the earlier smokebrook/lms-backend code; the rest (concept vector, expected information gain,
placement structure) is new because that code models a single ability number.
"""
from dataclasses import dataclass

import numpy as np

from app.mastery import core

GRID = np.linspace(-4.0, 4.0, 161)
MAX_ITEMS = 10
MCQ_ITEMS = 8  # the placement test ends with 10 - 8 = 2 short coding tasks (F-24)
MIN_ITEMS_BEFORE_STOP = 6
UNCERTAINTY_STOP_BITS = 0.5
SHORT_CODING_MAX_DIFFICULTY = 0.5
EVIDENCE_TYPE = {"mcq": "diagnostic_mcq", "code": "diagnostic_code"}


@dataclass(frozen=True)
class Item:
    id: int
    kind: str  # "mcq" or "code"
    a: float
    b: float
    concepts: dict[int, float]  # concept id -> weight


def prob_correct(theta: float, a: float, b: float) -> float:
    return float(1.0 / (1.0 + np.exp(-a * (theta - b))))


def fisher_information(theta: float, a: float, b: float) -> float:
    p = prob_correct(theta, a, b)
    return a * a * p * (1.0 - p)


def observed_probability(theta: float, a: float, b: float, kind: str) -> float:
    """P(correct answer) including guessing and slipping, with the mastery update's own rates."""
    slip, guess = core.DEFAULT_PARAMS[EVIDENCE_TYPE[kind]]
    return guess + (1.0 - slip - guess) * prob_correct(theta, a, b)


def eap_theta(responses: list[tuple[float, float, bool, str]], prior_sd: float = 1.0) -> float:
    """Posterior mean ability under a N(0, prior_sd^2) prior (TR-M-10).

    Responses are (a, b, correct, kind). With no prior a streak of identical answers sends the
    estimate to the bounds; the prior keeps short tests near the population mean until evidence
    accumulates. Guessing is modelled because a four-option item is right a quarter of the time by chance.
    """
    log_post = -0.5 * (GRID / prior_sd) ** 2
    for a, b, correct, kind in responses:
        slip, guess = core.DEFAULT_PARAMS[EVIDENCE_TYPE[kind]]
        p = guess + (1.0 - slip - guess) / (1.0 + np.exp(-a * (GRID - b)))
        log_post = log_post + np.log(p if correct else 1.0 - p)
    weights = np.exp(log_post - log_post.max())
    return float(np.sum(GRID * weights) / np.sum(weights))


def entropy(p: float) -> float:
    p = min(1 - 1e-9, max(1e-9, p))
    return float(-(p * np.log2(p) + (1 - p) * np.log2(1 - p)))


def expected_information_gain(item: Item, mastery: dict[int, float], theta: float) -> float:
    """Expected drop in entropy over the item's concepts, with the answer predicted by the 2PL."""
    slip, guess = core.DEFAULT_PARAMS[EVIDENCE_TYPE[item.kind]]
    p_right = observed_probability(theta, item.a, item.b, item.kind)
    gain = 0.0
    for concept, weight in item.concepts.items():
        p = mastery[concept]
        w = min(1.0, weight)
        after_right = core.weighted_update(p, slip, guess, True, w)
        after_wrong = core.weighted_update(p, slip, guess, False, w)
        gain += entropy(p) - p_right * entropy(after_right) - (1 - p_right) * entropy(after_wrong)
    return gain


def slot_kind(items_asked: int) -> str:
    return "mcq" if items_asked < MCQ_ITEMS else "code"


def eligible(items: list[Item], asked: set[int]) -> list[Item]:
    """Items allowed in the next slot: tracing items first, then short coding tasks."""
    kind = slot_kind(len(asked))
    return [
        i for i in items
        if i.id not in asked and i.kind == kind
        and (kind == "mcq" or i.b <= SHORT_CODING_MAX_DIFFICULTY)
    ]


def select_next(
    items: list[Item], asked: set[int], mastery: dict[int, float], theta: float
) -> Item | None:
    candidates = eligible(items, asked)
    if not candidates:
        return None
    # max() keeps the first of equal scores, and items arrive sorted by id: selection is deterministic.
    return max(candidates, key=lambda i: expected_information_gain(i, mastery, theta))


def uncertain_enough_to_stop(mastery: dict[int, float], items_asked: int) -> bool:
    """Stop early when even the three most uncertain concepts are well determined."""
    if items_asked < MIN_ITEMS_BEFORE_STOP:
        return False
    top = sorted((entropy(p) for p in mastery.values()), reverse=True)[:3]
    return float(np.mean(top)) < UNCERTAINTY_STOP_BITS


def finished(items_asked: int, mastery: dict[int, float]) -> bool:
    return items_asked >= MAX_ITEMS or uncertain_enough_to_stop(mastery, items_asked)
