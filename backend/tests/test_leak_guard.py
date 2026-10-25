"""TR-L-06, F-44: the leak guard allows short pointers and blocks solution code."""
import json
from pathlib import Path

import pytest

from app.feedback import leak

ROOT = Path(__file__).resolve().parents[1]
BANK = next(p for p in (ROOT / "data" / "bank", ROOT.parent / "data" / "bank") if p.exists())
REFERENCE = "n = int(input())\ntotal = 0\nfor i in range(1, n + 1):\n    total += i\nprint(total)\n"
FENCE = "`" * 3


def references() -> list[tuple[str, str]]:
    out = []
    for path in sorted((BANK / "problems").glob("*.json")):
        out += [(p["title"], p["reference_solution"]) for p in json.loads(path.read_text())]
    return out


@pytest.mark.parametrize(
    "text",
    [
        "The loop stops one value early because `range` leaves out its upper limit.",
        "Try `range(1, n + 1)` so that n itself is included.",
        "Your total is reset on every pass; start it before the loop with `total = 0`.",
        "Compare `n + 1` with what the loop produces for the smallest input.",
        "Line 3 repeats the wrong number of times.",
    ],
)
def test_short_pointers_are_allowed(text):
    assert leak.check(text, REFERENCE).passed, leak.check(text, REFERENCE).reason


def test_fenced_code_is_rejected():
    assert not leak.check(f"Do this:\n{FENCE}\nprint(1)\n{FENCE}", REFERENCE).passed


def test_more_than_a_few_lines_of_code_is_rejected():
    four_lines = "Try:\n    a = 1\n    b = 2\n    c = 3\n    d = 4"
    result = leak.check(four_lines, REFERENCE)
    assert not result.passed and "lines of code" in result.reason


def test_a_long_inline_snippet_is_rejected():
    long = "`" + "total = total + i + i + i + i + i + i + i + i + i + i + i + i" + "`"
    assert not leak.check(f"Write {long}", REFERENCE).passed


def test_the_reference_solution_itself_is_rejected():
    assert not leak.check(REFERENCE, REFERENCE).passed


def test_three_verbatim_lines_of_the_solution_are_rejected():
    assert not leak.check("The key part is:\n    for i in range(1, n + 1):\n        total += i\n    print(total)", REFERENCE).passed


def test_renamed_variables_do_not_hide_a_copy():
    renamed = "s = 0\nfor k in range(1, m + 1):\n    s += k\nprint(s)"
    assert not leak.check(renamed, REFERENCE).passed


def test_normalisation_ignores_names_numbers_and_strings():
    assert leak.normalise_tokens("x = 5") == leak.normalise_tokens("count = 99")
    assert leak.normalise_tokens("print('a')") == leak.normalise_tokens('print("zzz")')


def test_every_reference_solution_in_the_bank_is_caught_when_pasted_whole():
    missed = [title for title, ref in references() if leak.check(ref, ref).passed]
    assert missed == []


def test_short_one_line_fragments_are_never_blocked_by_the_similarity_rule():
    for fragment in ("`for i in range(n):`", "`total += i`", "`return result`", "`print(total)`"):
        assert leak.check(f"Look at {fragment}", REFERENCE).passed, fragment


TINY = "print(int(input()) + 1)\n"


@pytest.mark.parametrize(
    "text",
    ["Just write `print(int(input()) + 1)` and you are done.", "The answer is\nprint(int(input()) + 1)"],
)
def test_a_solution_shorter_than_the_usual_minimum_is_still_a_leak_when_pasted_whole(text):
    assert not leak.check(text, TINY).passed


@pytest.mark.parametrize("text", ["Convert it with `int(input())` first.", "Then add one to the number you read."])
def test_a_pointer_into_a_tiny_solution_still_passes(text):
    assert leak.check(text, TINY).passed


NOTES_WITH_SOLUTION = (
    "A worked example for this exercise:\n" + FENCE + "python\n" + REFERENCE + FENCE + "\nThe loop adds each number."
)
NOTES_WITH_SNIPPET = (
    "Dictionaries map keys to values:\n" + FENCE + "python\nd = {'a': 1}\nprint(d.get('b', 0))\n" + FENCE + "\nUse get for a default."
)


def test_a_notes_section_that_holds_the_solution_is_recognised_but_a_generic_example_is_not():
    assert leak.copies_reference(NOTES_WITH_SOLUTION, REFERENCE)
    assert not leak.copies_reference(NOTES_WITH_SNIPPET, REFERENCE)
    assert not leak.copies_reference("Review how loops repeat a block of code.", REFERENCE)


def test_the_concept_hint_skips_notes_that_contain_the_solution(monkeypatch):
    from types import SimpleNamespace

    from app.feedback import hints
    from app.retrieval.store import Source

    ctx = SimpleNamespace(
        primary_concept_name="loops", course_id=1, retrieval_query="loops", primary_concept_id=1,
        reference_solution=REFERENCE, leak_threshold=0.7, language="python")
    leaking = Source(1, "Loops", "Worked example", NOTES_WITH_SOLUTION, 0.9, 1)
    harmless = Source(2, "Loops", "Range", NOTES_WITH_SNIPPET, 0.8, 1)

    monkeypatch.setattr(hints.store, "search", lambda *a, **k: [leaking, harmless])
    assert hints.concept_hint(None, ctx).text == harmless.text
    monkeypatch.setattr(hints.store, "search", lambda *a, **k: [leaking])
    assert hints.concept_hint(None, ctx).text == "Review the course notes on loops."
