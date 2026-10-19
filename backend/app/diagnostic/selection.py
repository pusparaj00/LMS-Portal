"""Cold-start placement test: the choice of the next question and when to stop (F-20 to F-27, TR-M-03, TR-M-13).

The test draws on the course's own questions in three difficulty bands. The student's answers are turned into a pooled
estimate (app.diagnostic.pooled), one ability per concept with the abilities correlated. Each next question is scored
by how many of its concepts have no evidence yet (coverage) and by how much it is expected to shrink the uncertainty of
that estimate (expected information gain). That gain depends on the current ability estimate, so the test moves up after
right answers and down after wrong ones. Among the questions scoring within 10% of the best, one is chosen by a
generator seeded from the session, so two students with the same answers still meet different questions in a different
order.

The 2PL probability and the one-number ability estimate (`eap_theta`, shown to the student as their ability) follow the
formulas in the earlier smokebrook/lms-backend code.
"""
import random
from dataclasses import dataclass

import numpy as np

from app.diagnostic import pooled
from app.mastery import core

GRID = np.linspace(-4.0, 4.0, 161)
MAX_ITEMS = 20
MAX_MCQ = 14
MAX_CODE = 6
MAX_HARD_CODE = 2
WARMUP_ITEMS = 4  # tracing questions only, so nobody starts by writing code
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


Response = tuple[int, bool, str]  # (question id, answered correctly, evidence type)


def concept_index(items: list[Item]) -> dict[int, int]:
    return {c: n for n, c in enumerate(sorted({c for i in items for c in i.concepts}))}


def _question(item: Item, index: dict[int, int], evidence: str) -> pooled.Question:
    slip, guess = _params(evidence)
    return pooled.Question({index[c]: w for c, w in item.concepts.items()}, item.a, item.b, slip, guess)


def posterior(
    items: list[Item], responses: list[Response], prior_mean: float = 0.0, **prior
) -> tuple[dict[int, int], np.ndarray, np.ndarray]:
    """The pooled estimate of the abilities (concept index, mean, covariance) from the answers so far."""
    index = concept_index(items)
    by_id = {i.id: i for i in items}
    answers = []
    for item_id, correct, evidence in responses:
        q = _question(by_id[item_id], index, evidence)
        answers.append(pooled.Answer(q.weights, q.a, q.b, q.slip, q.guess, correct))
    theta, covariance = pooled.fit(answers, len(index), prior_mean, **prior)
    return index, theta, covariance


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
    items: list[Item], responses: list[Response], seed: str, prior_mean: float = 0.0, **prior
) -> Item | None:
    asked = [r[0] for r in responses]
    candidates = allowed(items, asked)
    if not candidates:
        return None
    candidates.sort(key=lambda i: i.id)
    index, theta, covariance = posterior(items, responses, prior_mean, **prior)
    current = pooled.mastery(theta, covariance)
    seen = covered(items, asked)
    cover = np.array([
        sum(w for c, w in i.concepts.items() if c not in seen) / (sum(i.concepts.values()) or 1.0) for i in candidates
    ])
    gain = np.array([
        pooled.expected_gain(_question(i, index, EVIDENCE_TYPE[i.kind]), theta, covariance, current) for i in candidates
    ])
    score = cover + gain / (gain.max() or 1.0)
    near = [i for i, s in zip(candidates, score, strict=True) if s >= NEAR_BEST * score.max()]
    return random.Random(f"{seed}:{len(asked)}").choice(near)


def max_questions(items: list[Item]) -> int:
    """How long the test can be for this course: at most MAX_ITEMS, fewer when the course has fewer usable questions."""
    mcq = sum(1 for i in items if i.kind == "mcq")
    code = sum(1 for i in items if i.kind == "code")
    return min(MAX_ITEMS, min(MAX_MCQ, mcq) + min(MAX_CODE, code))


def should_stop(items: list[Item], responses: list[Response], limit: int | None = None) -> bool:
    """The test runs to the longest the course allows. An earlier stop on "uncertainty is low" was measured and removed:
    after 16 questions the three least certain concepts still have a spread of 0.46 to 0.49 for every simulated student
    (docs/results/step-56-pooled-model.md), so no threshold separates students who could stop."""
    asked = [r[0] for r in responses]
    length = min(limit, max_questions(items)) if limit else max_questions(items)
    return len(asked) >= length or not allowed(items, asked)
