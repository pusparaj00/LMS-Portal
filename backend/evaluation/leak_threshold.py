"""Choose the leak guard's similarity threshold on the question bank (TR-L-06).

Usage (from backend/): python -m evaluation.leak_threshold
Positives are real solution code (a whole reference solution, and every 3-line window of it) that must be
blocked. Negatives are ordinary explanations and the short snippets used in the course notes, which must pass.
"""
import json
import re
from pathlib import Path

from app.feedback import leak

ROOT = Path(__file__).resolve().parents[1]
DATA = next(p for p in (ROOT / "data", ROOT.parent / "data") if p.exists())
THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

EXPLANATIONS = [
    "The loop stops one value early because `range` leaves out its upper limit.",
    "Your total is reset on every pass; start it before the loop with `total = 0`.",
    "The condition on that line uses `>` where the boundary value needs `>=`.",
    "A dictionary raises a KeyError for a missing key; `get` with a default avoids that.",
    "You print inside the loop, so the answer appears many times; print once after it ends.",
    "`input()` returns text, so convert it with `int(...)` before adding.",
    "The base case never returns a value, so the recursive call result is lost.",
    "Slicing with `[::-1]` reverses a string, but check what you do with the result.",
    "The function prints its answer, but the caller expects it to return one.",
    "The list is shared between the two names, so changing one changes the other.",
    "Look at the first line of the loop and think about which values it visits.",
    "Compare `len(words)` with the number of items you expect for the empty input.",
]


def references() -> list[tuple[str, str]]:
    out = []
    for path in sorted((DATA / "bank" / "problems").glob("*.json")):
        out += [(p["title"], p["reference_solution"]) for p in json.loads(path.read_text())]
    return out


def windows(code: str, size: int = 3) -> list[str]:
    lines = [line for line in code.splitlines() if line.strip()]
    return ["\n".join(lines[i : i + size]) for i in range(max(0, len(lines) - size + 1))]


def note_snippets() -> list[str]:
    spans = []
    for path in sorted((DATA / "notes").glob("*.md")):
        spans += re.findall(r"`([^`\n]+)`", path.read_text(encoding="utf-8"))
    return sorted(set(spans))


def main() -> None:
    refs = references()
    positives = []  # (reference, code that must be blocked)
    for _, ref in refs:
        positives.append((ref, ref))
        positives += [(ref, w) for w in windows(ref) if len(leak.normalise_tokens(w)) >= leak.MIN_TOKENS_TO_COMPARE]
    negatives = [(refs[i % len(refs)][1], f"Think about this: {e}") for i, e in enumerate(EXPLANATIONS)]
    negatives += [(refs[i % len(refs)][1], f"Look at `{s}`") for i, s in enumerate(note_snippets())]
    cross = [
        (ref, w)
        for i, (_, ref) in enumerate(refs)
        for j, (_, other) in enumerate(refs)
        if i != j
        for w in windows(other)
        if len(leak.normalise_tokens(w)) >= leak.MIN_TOKENS_TO_COMPARE
    ]
    print(f"{len(refs)} reference solutions, {len(positives)} solution fragments, {len(negatives)} ordinary texts, "
          f"{len(cross)} fragments of other problems")
    print("\n| Threshold | Solution code let through | Ordinary text blocked | Other problems' code blocked |")
    print("| --- | --- | --- | --- |")
    original = leak.SIMILARITY_THRESHOLD
    for threshold in THRESHOLDS:
        leak.SIMILARITY_THRESHOLD = threshold
        missed = sum(leak.check(code, ref).passed for ref, code in positives)
        wrong = sum(not leak.check(text, ref).passed for ref, text in negatives)
        other = sum(not leak.check(code, ref).passed for ref, code in cross)
        print(f"| {threshold} | {missed} of {len(positives)} | {wrong} of {len(negatives)} | {other} of {len(cross)} |")
    leak.SIMILARITY_THRESHOLD = original
    print(f"\nthreshold in use: {original}")


if __name__ == "__main__":
    main()
