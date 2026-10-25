"""Question bank import and validation (TR-D-03, TR-D-04, TR-V-02).

Usage: python -m app.bank_import data/bank [--dry-run] [--instructor EMAIL]
Every problem is validated first (reference solution must pass every test inside the sandbox).
Rejected problems are listed and never loaded; the exit code is 1 if any was rejected.
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, text

from app.db import get_engine
from app.mastery.core import DEFAULT_PARAMS
from app.services.problems import save_problem
from app.services.validation import validate_code_problem, validate_mcq_item


@dataclass
class Bank:
    course_title: str
    concepts: list[dict]
    misconceptions: list[dict]
    evidence_map: list[dict]
    problems: list[dict]
    items: list[dict]
    language: str = "python"


@dataclass
class Verdict:
    kind: str
    title: str
    errors: list[str] = field(default_factory=list)


def _with_statement(item: dict, language: str = "python") -> dict:
    fence = "```"
    return {**item, "statement": f"{item['question']}\n\n{fence}{language}\n{item['code']}{fence}"}


def load_bank(root: Path) -> Bank:
    problems = []
    for path in sorted((root / "problems").glob("*.json")):
        problems += json.loads(path.read_text())
    course = json.loads((root / "course.json").read_text())
    language = course.get("language", "python")
    return Bank(
        course_title=course["title"],
        concepts=json.loads((root / "concepts.json").read_text()),
        misconceptions=json.loads((root / "misconceptions.json").read_text()),
        evidence_map=json.loads((root / "evidence_map.json").read_text()),
        problems=problems,
        items=[_with_statement(i, language) for i in json.loads((root / "items.json").read_text())],
        language=language,
    )


def validate_bank(bank: Bank) -> list[Verdict]:
    concepts = {c["name"] for c in bank.concepts}
    misconceptions = {m["name"] for m in bank.misconceptions}
    verdicts = []
    for p in bank.problems:
        errors = validate_code_problem(
            concept_names=[c["name"] for c in p["concepts"]],
            known_concepts=concepts,
            reference_solution=p.get("reference_solution", ""),
            tests=p.get("tests", []),
            language=bank.language,
        )
        verdicts.append(Verdict("code", p["title"], errors))
    for item in bank.items:
        errors = validate_mcq_item(
            concept_names=[c["name"] for c in item["concepts"]],
            known_concepts=concepts,
            options=item["options"],
            known_misconceptions=misconceptions,
            code=item["code"],
            language=bank.language,
        )
        verdicts.append(Verdict("mcq", item["title"], errors))
    return verdicts


def _concept_ids(conn: Connection, course_id: int, concepts: list[dict]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for c in concepts:
        ids[c["name"]] = conn.execute(
            text(
                "INSERT INTO concepts (course_id, name) VALUES (:c, :n)"
                " ON CONFLICT (course_id, name) DO UPDATE SET name = excluded.name RETURNING id"
            ),
            {"c": course_id, "n": c["name"]},
        ).scalar_one()
    for c in concepts:
        conn.execute(
            text("UPDATE concepts SET parent_ids = :p WHERE id = :id"),
            {"p": [ids[parent] for parent in c.get("parents", [])], "id": ids[c["name"]]},
        )
    return ids


def _seed_mastery_config(conn: Connection, bank: Bank, concept_ids: dict[str, int]) -> None:
    """Default slip and guess per concept and evidence type (kept if already tuned), and the map."""
    for concept_id in concept_ids.values():
        for evidence_type, (slip, guess) in DEFAULT_PARAMS.items():
            conn.execute(
                text(
                    "INSERT INTO mastery_params (concept_id, evidence_type, slip, guess)"
                    " VALUES (:c, :e, :s, :g) ON CONFLICT DO NOTHING"
                ),
                {"c": concept_id, "e": evidence_type, "s": slip, "g": guess},
            )
    for row in bank.evidence_map:
        conn.execute(
            text(
                "INSERT INTO evidence_concept_map (test_category, error_type, concept_id, weight)"
                " VALUES (:c, :e, :k, :w) ON CONFLICT (test_category, error_type, concept_id)"
                " DO UPDATE SET weight = excluded.weight"
            ),
            {"c": row["category"], "e": row["error"], "k": concept_ids[row["concept"]], "w": row["weight"]},
        )


def import_bank(
    conn: Connection, bank: Bank, valid_titles: set[str], instructor_email: str
) -> dict:
    instructor_id = conn.execute(
        text("SELECT id FROM users WHERE email = lower(:e) AND role = 'instructor'"),
        {"e": instructor_email},
    ).scalar()
    if instructor_id is None:
        raise SystemExit(f"no instructor account {instructor_email}; run app.manage create-user")
    course_id = conn.execute(
        text("SELECT id FROM courses WHERE title = :t AND instructor_id = :i"),
        {"t": bank.course_title, "i": instructor_id},
    ).scalar()
    if course_id is None:
        course_id = conn.execute(
            text("INSERT INTO courses (title, instructor_id, language) VALUES (:t, :i, :l) RETURNING id"),
            {"t": bank.course_title, "i": instructor_id, "l": bank.language},
        ).scalar_one()

    concept_ids = _concept_ids(conn, course_id, bank.concepts)
    misconception_ids = {}
    for m in bank.misconceptions:
        misconception_ids[m["name"]] = conn.execute(
            text(
                "INSERT INTO misconceptions (concept_id, name, description) VALUES (:c, :n, :d)"
                " ON CONFLICT (concept_id, name) DO UPDATE SET description = excluded.description RETURNING id"
            ),
            {"c": concept_ids[m["concept"]], "n": m["name"], "d": m["description"]},
        ).scalar_one()

    _seed_mastery_config(conn, bank, concept_ids)

    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for kind, entries in (("code", bank.problems), ("mcq", bank.items)):
        for e in entries:
            if e["title"] not in valid_titles:
                continue
            _, status = save_problem(
                conn,
                course_id=course_id,
                title=e["title"],
                statement=e["statement"],
                kind=kind,
                difficulty_b=e["difficulty_b"],
                discrimination_a=e["discrimination_a"],
                param_source="prior",
                reference_solution=e.get("reference_solution"),
                concept_weights=[(concept_ids[c["name"]], c["weight"]) for c in e["concepts"]],
                tests=e.get("tests", []),
                options=[
                    {
                        "text": o["text"],
                        "correct": o["correct"],
                        "misconception_id": misconception_ids.get(o.get("misconception")),
                    }
                    for o in e.get("options", [])
                ],
            )
            counts[status] += 1
    return {"course_id": course_id, **counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bank_dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--instructor")
    args = parser.parse_args()

    bank = load_bank(args.bank_dir)
    verdicts = validate_bank(bank)
    for v in verdicts:
        print(f"{'OK      ' if not v.errors else 'REJECTED'} {v.kind:4} {v.title}")
        for error in v.errors:
            print(f"           - {error}")
    valid = [v for v in verdicts if not v.errors]
    print(
        f"validated {len(valid)} of {len(verdicts)} "
        f"({sum(v.kind == 'code' for v in valid)} code problems, "
        f"{sum(v.kind == 'mcq' for v in valid)} tracing items)"
    )

    if not args.dry_run:
        if not args.instructor:
            parser.error("--instructor is required unless --dry-run")
        with get_engine().begin() as conn:
            print(import_bank(conn, bank, {v.title for v in valid}, args.instructor))
    return 0 if len(valid) == len(verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
