"""Cold-start placement test: the maths and the choice of the next question (F-20 to F-27, TR-M-03, TR-M-10, TR-M-13).

The 2PL probability, Fisher information and prior-regularised ability estimate follow the formulas in the earlier
smokebrook/lms-backend code; the rest (concept vector, expected information gain, the shape of the test) is new because
that code models a single ability number.

The test draws on the course's own questions in three difficulty bands. Each next question is scored by how many of its
concepts have no evidence yet (coverage), how much it tells us about this student's ability (Fisher information at the
current estimate, which moves the test up after right answers and down after wrong ones) and how much it would sharpen
the concept vector (expected information gain). Among the questions scoring within 10% of the best, one is chosen by a
generator seeded from the session, so two students with the same answers still meet different questions in a different
order.
"""
import random
from dataclasses import dataclass

import numpy as np

from app.mastery import core

GRID = np.linspace(-4.0, 4.0, 161)
MIN_ITEMS = 16
MAX_ITEMS = 20
MAX_MCQ = 14
MAX_CODE = 6
MAX_HARD_CODE = 2
WARMUP_ITEMS = 4  # tracing questions only, so nobody starts by writing code
UNCERTAINTY_STOP_BITS = 0.5
NEAR_BEST = 0.9
EASY_BELOW = -0.5
HARD_ABOVE = 0.5
BACKGROUND_PRIOR_MEAN = {"new": -0.7, "some": 0.0, "comfortable": 0.5}
EVIDENCE_TYPE = {"mcq": "diagnostic_mcq", "code": "diagnostic_code"}


@dataclass(frozen=True)
class Item:
    id: int
    kind: str  # "mcq" or "code"
    a: float
    b: float
    concepts: dict[int, float]  # concept id -> weight


def band(b: float) -> str:
    return "easy" if b < EASY_BELOW else "hard" if b > HARD_ABOVE else "medium"


def prob_correct(theta: float, a: float, b: float) -> float:
    return float(1.0 / (1.0 + np.exp(-a * (theta - b))))


def fisher_information(theta: float, a: float, b: float) -> float:
    p = prob_correct(theta, a, b)
    return a * a * p * (1.0 - p)


def _params(evidence: str) -> tuple[float, float]:
    """Slip and guess of an evidence type, or of the placement type of an item kind."""
    return core.DEFAULT_PARAMS[EVIDENCE_TYPE.get(evidence, evidence)]


def observed_probability(theta: float, a: float, b: float, kind: str) -> float:
    """P(correct answer) including guessing and slipping, with the mastery update's own rates."""
    slip, guess = _params(kind)
    return guess + (1.0 - slip - guess) * prob_correct(theta, a, b)


def eap_theta(
    responses: list[tuple[float, float, bool, str]], prior_sd: float = 1.0, prior_mean: float = 0.0
) -> float:
    """Posterior mean ability under a N(prior_mean, prior_sd^2) prior (TR-M-10).

    Responses are (a, b, correct, kind or evidence type). With no prior a streak of identical answers sends the
    estimate to the bounds; the prior keeps short tests near the starting point until evidence accumulates. Guessing is
    modelled because a four-option item is right a quarter of the time by chance, and a "don't know" has no guess
    chance.
    The starting point is the population mean, or the one the student's background answer sets (F-26).
    """
    log_post = -0.5 * ((GRID - prior_mean) / prior_sd) ** 2
    for a, b, correct, evidence in responses:
        slip, guess = _params(evidence)
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


def covered(items: list[Item], asked: list[int]) -> set[int]:
    """Concepts that at least one asked question touched."""
    by_id = {i.id: i for i in items}
    return {c for a in asked if a in by_id for c in by_id[a].concepts}


def allowed(items: list[Item], asked: list[int]) -> list[Item]:
    """Questions that may come next: not asked, within the type limits, tracing first, never two coding tasks in a row
    while a tracing question is left (TR-M-13)."""
    by_id = {i.id: i for i in items}
    done = [by_id[a] for a in asked if a in by_id]
    mcq = sum(1 for i in done if i.kind == "mcq")
    code = sum(1 for i in done if i.kind == "code")
    hard_code = sum(1 for i in done if i.kind == "code" and band(i.b) == "hard")
    pool = [
        i for i in items
        if i.id not in set(asked)
        and (i.kind == "mcq" and mcq < MAX_MCQ
             or i.kind == "code" and code < MAX_CODE and not (band(i.b) == "hard" and hard_code >= MAX_HARD_CODE))
    ]
    tracing = [i for i in pool if i.kind == "mcq"]
    if tracing and (len(asked) < WARMUP_ITEMS or (done and done[-1].kind == "code")):
        return tracing
    return pool


def select_next(
    items: list[Item], asked: list[int], mastery: dict[int, float], theta: float, seed: str
) -> Item | None:
    candidates = allowed(items, asked)
    if not candidates:
        return None
    candidates.sort(key=lambda i: i.id)
    seen = covered(items, asked)
    cover = [
        sum(w for c, w in i.concepts.items() if c not in seen) / (sum(i.concepts.values()) or 1.0) for i in candidates
    ]
    info = np.array([fisher_information(theta, i.a, i.b) for i in candidates])
    gain = np.array([expected_information_gain(i, mastery, theta) for i in candidates])
    score = np.array(cover) + info / (info.max() or 1.0) + gain / (gain.max() or 1.0)
    near = [i for i, s in zip(candidates, score, strict=True) if s >= NEAR_BEST * score.max()]
    return random.Random(f"{seed}:{len(asked)}").choice(near)


def settled(mastery: dict[int, float]) -> bool:
    """Even the three most uncertain concepts are well determined."""
    top = sorted((entropy(p) for p in mastery.values()), reverse=True)[:3]
    return float(np.mean(top)) < UNCERTAINTY_STOP_BITS


def max_questions(items: list[Item]) -> int:
    """How long the test can be for this course: at most MAX_ITEMS, fewer when the course has fewer usable questions."""
    mcq = sum(1 for i in items if i.kind == "mcq")
    code = sum(1 for i in items if i.kind == "code")
    return min(MAX_ITEMS, min(MAX_MCQ, mcq) + min(MAX_CODE, code))


def should_stop(items: list[Item], asked: list[int], mastery: dict[int, float]) -> bool:
    """Stop at the longest the course allows, or from the minimum once every concept has evidence and the rest is
    settled."""
    total = max_questions(items)
    if len(asked) >= total or not allowed(items, asked):
        return True
    minimum = min(MIN_ITEMS, total)
    every_concept = {c for i in items for c in i.concepts} <= covered(items, asked)
    return len(asked) >= minimum and every_concept and settled(mastery)
