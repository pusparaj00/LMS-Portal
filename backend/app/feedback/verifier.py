"""Deterministic verifier for an explanation (TR-L-04, TR-L-06, F-43). Plain code, no second LLM.

Every check is independent so the log shows exactly which one failed.
"""
import json
from dataclasses import dataclass

from app.feedback import leak

MAX_CLAIM_CHARS = 400
ALLOWED_HINT_LEVELS = {1, 2}  # level 3 is the worked example, which never comes from the model
MIN_HIDDEN_TEXT = 4  # shorter hidden values (such as "0") would match ordinary words
MAX_EXAMPLE_CHARS = 300  # an input a student could type; also keeps the sandbox runs small

REQUIRED = {
    "failing_test_id": int,
    "line": int,
    "concept_id": int,
    "claim": str,
    "source_chunk_ids": list,
    "hint_level": int,
}

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "failing_test_id": {"type": "integer"},
        "line": {"type": "integer"},
        "concept_id": {"type": "integer"},
        "claim": {"type": "string"},
        "source_chunk_ids": {"type": "array", "items": {"type": "integer"}},
        "hint_level": {"type": "integer"},
        "example_input": {"type": "string"},
    },
    "required": list(REQUIRED),
}


@dataclass(frozen=True)
class FailedTest:
    id: int
    category: str
    hidden: bool
    input: str
    expected: str
    concept_ids: frozenset[int]  # concepts linked to this test's failed category


@dataclass(frozen=True)
class Evidence:
    """Everything the verifier is allowed to compare an explanation against."""

    code: str
    reference_solution: str
    failed_tests: list[FailedTest]
    error_concept_ids: frozenset[int]  # concepts linked to the run's error type, if it had one
    retrieved_chunk_ids: frozenset[int]
    hidden_inputs: frozenset[str] = frozenset()  # every hidden test input of the problem, passed or failed
    error_type: str | None = None  # the run's error_type, used to keep syntax errors on the syntax concept
    leak_threshold: float = leak.SIMILARITY_THRESHOLD  # the problem's leak policy (F-62)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class Explanation:
    failing_test_id: int
    line: int
    concept_id: int
    claim: str
    source_chunk_ids: list[int]
    hint_level: int
    example_input: str = ""  # optional: an input on which the claim says the program goes wrong (TR-L-05)


def parse(raw: str) -> tuple[Explanation | None, Check]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, Check("json_valid", False, "reply is not valid JSON")
    if not isinstance(data, dict):
        return None, Check("json_valid", False, "reply is not a JSON object")
    for key, kind in REQUIRED.items():
        value = data.get(key)
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            return None, Check("json_valid", False, f"field '{key}' is missing or not a {kind.__name__}")
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in data["source_chunk_ids"]):
        return None, Check("json_valid", False, "source_chunk_ids must be integers")
    example = data.get("example_input")
    if example is not None and not isinstance(example, str):
        return None, Check("json_valid", False, "field 'example_input' must be text")
    return Explanation(**{k: data[k] for k in REQUIRED}, example_input=example or ""), Check("json_valid", True)


def verify(raw: str, evidence: Evidence) -> tuple[Explanation | None, list[Check]]:
    explanation, parsed = parse(raw)
    if explanation is None:
        return None, [parsed]
    failed = {t.id: t for t in evidence.failed_tests}
    test = failed.get(explanation.failing_test_id)
    lines = max(1, len(evidence.code.splitlines()))
    if evidence.error_type == "syntax_error":
        # A syntax error stops the whole program, so only the syntax concept may be named (TR-M-02).
        allowed_concepts = set(evidence.error_concept_ids)
    else:
        allowed_concepts = set(evidence.error_concept_ids) | (set(test.concept_ids) if test else set())
    hidden_secrets = {h.strip() for h in evidence.hidden_inputs}
    for t in evidence.failed_tests:
        if t.hidden:
            hidden_secrets.update(s.strip() for s in (t.input, t.expected))
    hidden_secrets = {s for s in hidden_secrets if len(s) >= MIN_HIDDEN_TEXT}
    leaked = [s for s in hidden_secrets if s in explanation.claim]
    example = explanation.example_input.strip()
    if example and example in hidden_secrets:
        leaked.append(example)  # the example would show a student a hidden test input or output
    guard = leak.check(explanation.claim, evidence.reference_solution, evidence.leak_threshold)
    unknown_chunks = sorted(set(explanation.source_chunk_ids) - evidence.retrieved_chunk_ids)
    example_ok = len(explanation.example_input) <= MAX_EXAMPLE_CHARS and "\x00" not in explanation.example_input

    checks = [
        parsed,
        Check("test_exists", test is not None, "" if test else f"test {explanation.failing_test_id} did not fail"),
        Check("line_exists", 1 <= explanation.line <= lines, f"line {explanation.line} of {lines}"),
        Check(
            "concept_matches",
            explanation.concept_id in allowed_concepts,
            f"concept {explanation.concept_id} not in {sorted(allowed_concepts)}",
        ),
        Check(
            "sources_real",
            not unknown_chunks,
            f"chunk ids not retrieved: {unknown_chunks}" if unknown_chunks else "",
        ),
        Check("hint_level_ok", explanation.hint_level in ALLOWED_HINT_LEVELS, f"hint_level {explanation.hint_level}"),
        Check(
            "claim_length",
            1 <= len(explanation.claim.strip()) <= MAX_CLAIM_CHARS,
            f"{len(explanation.claim.strip())} characters",
        ),
        Check("no_code_leak", guard.passed, guard.reason),
        Check("no_hidden_test_leak", not leaked, "claim or example repeats hidden test data" if leaked else ""),
        Check(
            "example_input_ok",
            example_ok,
            "" if example_ok else f"example_input is longer than {MAX_EXAMPLE_CHARS} characters or holds a NUL",
        ),
    ]
    return explanation, checks


def all_passed(checks: list[Check]) -> bool:
    return all(c.passed for c in checks)
