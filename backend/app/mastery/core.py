"""Mastery update rules (DRD section 4, TR-M-01, TR-M-07, TR-M-09). Pure functions, no I/O."""
from dataclasses import dataclass

EPS = 1e-6
PROPAGATION_FRACTION = 0.3  # share of a sharp drop passed to prerequisite concepts (F-33)
PROPAGATION_THRESHOLD = 0.1  # smallest drop that is passed on

# Default slip and guess per evidence type (DRD section 4). Weaker evidence has a higher slip, so
# a partial failure lowers mastery less than a total failure.
DEFAULT_PARAMS: dict[str, tuple[float, float]] = {
    "all_pass": (0.10, 0.20),
    "full_fail": (0.10, 0.20),
    "partial_fail": (0.30, 0.20),
    "syntax_error": (0.20, 0.20),
    "runtime_error": (0.25, 0.20),
    "time_limit": (0.30, 0.20),
    "output_limit": (0.30, 0.20),  # a runaway loop, like time_limit
    "memory_limit": (0.25, 0.20),  # a crash at run time, like runtime_error
    "diagnostic_mcq": (0.10, 0.25),
    "diagnostic_code": (0.10, 0.20),
    "probe_mcq": (0.10, 0.25),
    "probe_code": (0.10, 0.20),
}

# Misconception evidence: how likely a student with / without the misconception picks its option.
P_PICK_IF_HAS = 0.8
P_PICK_IF_NOT = 0.15
P_AVOID_IF_HAS = 0.2  # picks the correct option although holding the misconception


def clamp(p: float) -> float:
    return min(1.0 - EPS, max(EPS, p))


def bayes_update(p: float, slip: float, guess: float, correct: bool) -> float:
    """p' = p(1-s) / (p(1-s) + (1-p)g) if correct, p s / (p s + (1-p)(1-g)) if not."""
    if correct:
        numerator = p * (1 - slip)
        denominator = numerator + (1 - p) * guess
    else:
        numerator = p * slip
        denominator = numerator + (1 - p) * (1 - guess)
    return clamp(numerator / denominator)


def weighted_update(p: float, slip: float, guess: float, correct: bool, weight: float) -> float:
    """Move p towards the Bayesian posterior by `weight` (0 to 1), the concept's share of the item."""
    return clamp(p + weight * (bayes_update(p, slip, guess, correct) - p))


def misconception_update(probability: float, picked_its_option: bool, chose_correct: bool) -> float:
    """Posterior that the student holds a misconception after one answer to an item tagged with it."""
    if picked_its_option:
        likelihood_has, likelihood_not = P_PICK_IF_HAS, P_PICK_IF_NOT
    elif chose_correct:
        likelihood_has, likelihood_not = P_AVOID_IF_HAS, 1 - P_PICK_IF_NOT
    else:
        return probability
    numerator = probability * likelihood_has
    return clamp(numerator / (numerator + (1 - probability) * likelihood_not))


def propagated(parent_p: float, source_before: float, source_after: float) -> float | None:
    """New value for a prerequisite after a sharp drop in a dependent concept, or None."""
    drop = source_before - source_after
    if drop < PROPAGATION_THRESHOLD:
        return None
    return clamp(parent_p - PROPAGATION_FRACTION * drop)


@dataclass(frozen=True)
class Event:
    """One ledger row, as needed to replay it."""

    id: int
    concept_id: int
    rule_id: str
    evidence_type: str
    weight: float
    correct: bool | None
    p_before: float
    p_after: float
    source_event_id: int | None


def replay(
    priors: dict[int, float],
    events: list[Event],
    params: dict[tuple[int, str], tuple[float, float]],
) -> dict[int, float]:
    """Rebuild the mastery vector from the ledger: same priors and events, same vector (TR-M-09)."""
    state = dict(priors)
    by_id = {e.id: e for e in events}
    for event in sorted(events, key=lambda e: e.id):
        p = state.get(event.concept_id, priors[event.concept_id])
        if event.rule_id == "prerequisite_propagation":
            source = by_id[event.source_event_id]
            updated = propagated(p, source.p_before, source.p_after)
            state[event.concept_id] = p if updated is None else updated
        else:
            slip, guess = params[(event.concept_id, event.evidence_type)]
            state[event.concept_id] = weighted_update(p, slip, guess, bool(event.correct), event.weight)
    return state
