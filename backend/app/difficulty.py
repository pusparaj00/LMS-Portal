"""Initial difficulty estimates for new coding problems (F-23), from their text and concept tags.

A small ridge regression fitted on the vetted question bank: reference-solution length, nesting and control
structures, statement length, number of concepts, and the bank's average difficulty for the problem's concepts. No
model call; the same input always gives the same estimate. The bank's difficulties are its authors' judgement, not yet
calibrated on real answers (that is the pilot, TR-M-05), so an estimate imitates that judgement. A problem whose
difficulty was estimated is stored with param_source 'estimated' (TR-D-03).
"""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

CONTROL = re.compile(r"\b(if|elif|for|while|try|except|def|class|return|lambda|with)\b")
COMPREHENSION = re.compile(r"\[[^\]]*\bfor\b[^\]]*\]|\{[^}]*\bfor\b[^}]*\}")
RIDGE = 3.0  # chosen by leave-one-out on the bank, see evaluation/difficulty_model.py
LOW, HIGH = -2.0, 2.0  # the range the placement test's item model works in


class NoBank(Exception):
    pass


def _bank_dir() -> Path:
    here = Path(__file__).resolve().parents[1]
    for path in (here / "data" / "bank", here.parent / "data" / "bank", Path("/srv/data/bank")):
        if path.exists():
            return path
    raise NoBank("the question bank is not available, so a difficulty cannot be estimated; choose one instead")


def bank_problems() -> list[dict]:
    """The bank's coding problems, each with its statement, reference solution, concept names and difficulty."""
    problems = []
    for path in sorted((_bank_dir() / "problems").glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            if item.get("reference_solution"):
                problems.append({
                    "title": item["title"], "statement": item["statement"], "reference": item["reference_solution"],
                    "concepts": [c["name"] for c in item["concepts"]], "b": float(item["difficulty_b"]),
                })
    return problems


def text_features(statement: str, reference: str, concepts: list[str]) -> list[float]:
    lines = [line for line in reference.splitlines() if line.strip()]
    depth = max((len(line) - len(line.lstrip(" "))) // 4 for line in lines) if lines else 0
    control = len(CONTROL.findall(reference)) + len(COMPREHENSION.findall(reference))
    return [float(len(lines)), float(depth), float(control), float(len(statement.split())), float(len(concepts))]


def concept_prior(concepts: list[str], known: list[dict]) -> float:
    """The average difficulty of known problems sharing a concept with this one, or of all of them if none does."""
    names = {c.lower() for c in concepts}
    shared = [p["b"] for p in known if names & {c.lower() for c in p["concepts"]}]
    return float(np.mean(shared if shared else [p["b"] for p in known]))


@dataclass(frozen=True)
class Model:
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    intercept: float
    known: tuple

    def estimate(self, statement: str, reference: str, concepts: list[str]) -> float:
        x = np.array(text_features(statement, reference, concepts) + [concept_prior(concepts, list(self.known))])
        value = float(self.intercept + ((x - self.mean) / self.scale) @ self.weights)
        return round(min(HIGH, max(LOW, value)), 2)


def fit(problems: list[dict], ridge: float = RIDGE) -> Model:
    x = np.array([
        text_features(p["statement"], p["reference"], p["concepts"]) + [concept_prior(p["concepts"], problems)]
        for p in problems
    ])
    y = np.array([p["b"] for p in problems])
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1.0
    z = (x - mean) / scale
    weights = np.linalg.solve(z.T @ z + ridge * np.eye(z.shape[1]), z.T @ (y - y.mean()))
    return Model(mean, scale, weights, float(y.mean()), tuple(problems))


@lru_cache
def model() -> Model:
    return fit(bank_problems())


def estimate(statement: str, reference: str, concepts: list[str]) -> float:
    return model().estimate(statement, reference, concepts)
