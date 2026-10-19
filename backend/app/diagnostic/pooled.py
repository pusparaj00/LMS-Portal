"""Pooled concept estimate for the placement test (TR-M-15, TR-M-18).

Each concept has its own ability, and the abilities of one student are correlated, so an answer about loops also tells
us something about lists. Treating the concepts as independent (one Bayesian update per concept, as the mastery rule
does) wastes that: with 12 concepts and 16 to 20 questions each concept has only one or two answers behind it.

The model is a multidimensional 2PL: the chance of a right answer is guess + (1 - slip - guess) * logistic(D * a *
(weighted ability of the item's concepts - b)), with a Gaussian prior on the abilities whose pairwise correlation is
`correlation`. The posterior is found by Fisher scoring (a Gaussian approximation), which needs only numpy.
D = 1.7 is the usual constant that makes the logistic match the normal ogive.
"""
from dataclasses import dataclass

import numpy as np

D = 1.7
MASTERY_SLOPE = 1.7  # mastery of a concept = chance of right answer on an item with a = 1, b = 0 and no guessing
CORRELATION = 0.3  # chosen on training data only: docs/results/step-56-pooled-model.md
PRIOR_SD = 1.5
MAX_ITERATIONS = 40
MAX_STEP = 1.5


@dataclass(frozen=True)
class Question:
    weights: dict[int, float]  # concept index -> weight in the item
    a: float
    b: float
    slip: float
    guess: float


@dataclass(frozen=True)
class Answer(Question):
    correct: bool


def prior_covariance(k: int, correlation: float, sd: float) -> np.ndarray:
    return sd**2 * (correlation * np.ones((k, k)) + (1.0 - correlation) * np.eye(k))


def _design(answers: list[Question], k: int) -> np.ndarray:
    design = np.zeros((len(answers), k))
    for n, answer in enumerate(answers):
        total = sum(answer.weights.values())
        for concept, weight in answer.weights.items():
            design[n, concept] = weight / total
    return design


def fit(
    answers: list[Answer], k: int, prior_mean: float = 0.0, correlation: float = CORRELATION, sd: float = PRIOR_SD
) -> tuple[np.ndarray, np.ndarray]:
    """Posterior mean and covariance of the k concept abilities."""
    precision = np.linalg.inv(prior_covariance(k, correlation, sd))
    mean = np.full(k, float(prior_mean))
    theta = mean.copy()
    if not answers:
        return theta, np.linalg.inv(precision)
    design = _design(answers, k)
    a = np.array([x.a for x in answers])
    b = np.array([x.b for x in answers])
    slip = np.array([x.slip for x in answers])
    guess = np.array([x.guess for x in answers])
    y = np.array([x.correct for x in answers], dtype=float)
    span = 1.0 - slip - guess
    for _ in range(MAX_ITERATIONS):
        s = 1.0 / (1.0 + np.exp(-D * a * (design @ theta - b)))
        p = np.clip(guess + span * s, 1e-9, 1 - 1e-9)
        slope = span * s * (1.0 - s) * D * a
        score = slope * (y - p) / (p * (1.0 - p))
        information = slope**2 / (p * (1.0 - p))
        gradient = design.T @ score - precision @ (theta - mean)
        hessian = precision + design.T @ (design * information[:, None])
        step = np.linalg.solve(hessian, gradient)
        norm = float(np.max(np.abs(step)))
        theta = theta + (step if norm <= MAX_STEP else step * (MAX_STEP / norm))
        if norm < 1e-7:
            break
    s = 1.0 / (1.0 + np.exp(-D * a * (design @ theta - b)))
    p = np.clip(guess + span * s, 1e-9, 1 - 1e-9)
    information = (span * s * (1.0 - s) * D * a) ** 2 / (p * (1.0 - p))
    return theta, np.linalg.inv(precision + design.T @ (design * information[:, None]))


def mastery(theta: np.ndarray, covariance: np.ndarray, slope: float = MASTERY_SLOPE) -> np.ndarray:
    """Expected mastery of each concept, with the spread of the estimate taken into account (probit approximation)."""
    variance = np.diag(covariance)
    return 1.0 / (1.0 + np.exp(-slope * theta / np.sqrt(1.0 + np.pi * slope**2 * variance / 8.0)))


def estimate(
    answers: list[Answer], k: int, prior_mean: float = 0.0, correlation: float = CORRELATION, sd: float = PRIOR_SD
) -> np.ndarray:
    theta, covariance = fit(answers, k, prior_mean, correlation, sd)
    return mastery(theta, covariance)


def expected_gain(question: Question, theta: np.ndarray, covariance: np.ndarray, current_mastery: np.ndarray) -> float:
    """How much asking this question is expected to shrink the uncertainty of the mastery vector.

    The question adds Fisher information `info` along its concept weights w, so the posterior covariance shrinks by
    (S w)(S w)' * info / (1 + info * w'S w) (Sherman-Morrison). The shrinkage of each concept's variance is carried
    to the mastery scale by the slope of mastery at the current estimate and summed over concepts.
    """
    design = _design([question], len(theta))[0]
    z = 1.0 / (1.0 + np.exp(-D * question.a * (design @ theta - question.b)))
    span = 1.0 - question.slip - question.guess
    p = min(1 - 1e-9, max(1e-9, question.guess + span * z))
    info = (span * z * (1.0 - z) * D * question.a) ** 2 / (p * (1.0 - p))
    direction = covariance @ design
    shrink = info / (1.0 + info * float(design @ direction))
    slope = MASTERY_SLOPE * current_mastery * (1.0 - current_mastery)
    return float(np.sum(slope**2 * direction**2) * shrink)
