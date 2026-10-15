"""TR-L-01: the course notes are accurate. Every example in every note runs in the sandbox and prints what
the note says it prints, so the notes cannot drift from real Python behaviour."""
import json
import re
from pathlib import Path

import pytest

from app.grading import normalise
from app.retrieval.chunking import parse_note
from app.sandbox import run_batch

ROOT = Path(__file__).resolve().parents[1]
DATA = next(p for p in (ROOT / "data", ROOT.parent / "data") if (p / "notes").exists())
NOTES = sorted((DATA / "notes").glob("*.md"))
EXAMPLE = re.compile(r"```python\n(.*?)```\s*Output:\n```\n(.*?)```", re.DOTALL)


def examples():
    for path in NOTES:
        for n, (code, expected) in enumerate(EXAMPLE.findall(path.read_text(encoding="utf-8")), 1):
            yield pytest.param(code, expected, id=f"{path.stem}-{n}")


@pytest.mark.parametrize("code,expected", list(examples()))
def test_the_example_prints_what_the_note_says(code, expected):
    (run,) = run_batch(code, [""])
    assert run.status == "ok", run.stderr
    assert normalise(run.stdout) == normalise(expected)


def test_every_note_has_examples_and_stays_flagged_for_human_review():
    assert len(NOTES) == 8
    for path in NOTES:
        fields, _ = parse_note(path.read_text(encoding="utf-8"))
        assert fields["status"] == "needs human review", path.name
        assert EXAMPLE.search(path.read_text(encoding="utf-8")), f"{path.name} has no verified example"


def test_the_sections_the_retrieval_questions_point_at_still_exist():
    headings = {}
    for path in NOTES:
        fields, body = parse_note(path.read_text(encoding="utf-8"))
        headings[fields["title"]] = set(re.findall(r"^## +(.+)$", body, flags=re.MULTILINE))
    questions = json.loads((DATA / "eval" / "retrieval_questions.json").read_text(encoding="utf-8"))
    missing = [q["question"] for q in questions if q["section"] not in headings.get(q["note"], set())]
    assert missing == []
