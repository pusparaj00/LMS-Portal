"""Simulated students and the ground-truth response model (TR-V-05).

The truth model is deliberately different from the model that selects items and updates mastery:
  * selection/update: each concept is a probability updated with fixed slip and guess (BKT-style),
    items are chosen with a 2PL whose parameters are the bank's priors;
  * truth: students have CORRELATED CONTINUOUS concept abilities, responses follow a 2PL link on
    the item's weighted ability with PERTURBED item parameters and DIFFERENT slip and guess values.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.diagnostic.selection import Item

ABILITY_CORRELATION = 0.6  # share of each concept ability explained by a general factor
ITEM_A_SCALE = (0.7, 1.3)  # true discrimination = bank prior x U(...)
ITEM_B_NOISE_SD = 0.4  # true difficulty = bank prior + N(0, sd)
TRUE_SLIP = 0.15
TRUE_GUESS = {"mcq": 0.20, "code": 0.08}
MASTERY_SCALE = 2.0  # true mastery of a concept = sigmoid(MASTERY_SCALE * ability)


@dataclass(frozen=True)
class Bank:
    items: list[Item]
    concepts: list[str]
    parents: dict[int, list[int]]


def load_bank(bank_dir: Path) -> Bank:
    concept_rows = json.loads((bank_dir / "concepts.json").read_text())
    index = {c["name"]: i for i, c in enumerate(concept_rows)}
    raw = []
    for path in sorted((bank_dir / "problems").glob("*.json")):
        raw += [("code", p) for p in json.loads(path.read_text())]
    raw += [("mcq", i) for i in json.loads((bank_dir / "items.json").read_text())]
    items = [
        Item(
            id=n, kind=kind, a=p["discrimination_a"], b=p["difficulty_b"],
            concepts={index[c["name"]]: c["weight"] for c in p["concepts"]},
        )
        for n, (kind, p) in enumerate(raw)
    ]
    parents = {i: [index[p] for p in c.get("parents", [])] for i, c in enumerate(concept_rows)}
    return Bank(items, [c["name"] for c in concept_rows], parents)


def make_students(rng: np.random.Generator, n: int, concepts: int) -> np.ndarray:
    general = rng.normal(size=(n, 1))
    specific = rng.normal(size=(n, concepts))
    rho = ABILITY_CORRELATION
    return rho * general + np.sqrt(1 - rho**2) * specific


def true_mastery(theta: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-MASTERY_SCALE * theta))


def true_item_params(rng: np.random.Generator, items: list[Item]) -> tuple[np.ndarray, np.ndarray]:
    a = np.array([i.a for i in items]) * rng.uniform(*ITEM_A_SCALE, size=len(items))
    b = np.array([i.b for i in items]) + rng.normal(0, ITEM_B_NOISE_SD, size=len(items))
    return a, b


def response_probabilities(
    theta: np.ndarray, items: list[Item], a_true: np.ndarray, b_true: np.ndarray
) -> np.ndarray:
    """P(correct) for every student and item: shape (students, items)."""
    out = np.empty((theta.shape[0], len(items)))
    for n, item in enumerate(items):
        weights = np.array(list(item.concepts.values()))
        weights = weights / weights.sum()
        ability = theta[:, list(item.concepts)] @ weights
        link = 1.0 / (1.0 + np.exp(-1.7 * a_true[n] * (ability - b_true[n])))
        guess = TRUE_GUESS[item.kind]
        out[:, n] = guess + (1.0 - TRUE_SLIP - guess) * link
    return out
