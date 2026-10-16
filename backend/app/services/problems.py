from typing import Literal

from sqlalchemy import Connection, text

from app.schemas import ConceptTag, Problem, ProblemDetail

PROBLEM_COLUMNS = (
    "id, course_id, title, statement, language, kind, difficulty_b, discrimination_a, review_status,"
    " archived_at IS NOT NULL AS archived, param_source"
)


def _concepts(conn: Connection, problem_ids: list[int]) -> dict[int, list[ConceptTag]]:
    rows = conn.execute(
        text(
            "SELECT pc.problem_id, c.id, c.name, pc.weight FROM problem_concepts pc"
            " JOIN concepts c ON c.id = pc.concept_id WHERE pc.problem_id = ANY(:ids)"
            " ORDER BY c.name"
        ),
        {"ids": problem_ids},
    )
    out: dict[int, list[ConceptTag]] = {pid: [] for pid in problem_ids}
    for pid, cid, name, weight in rows:
        out[pid].append(ConceptTag(concept_id=cid, name=name, weight=weight))
    return out


def list_problems(conn: Connection, course_id: int, include_archived: bool = False) -> list[Problem]:
    rows = conn.execute(
        text(
            f"SELECT {PROBLEM_COLUMNS} FROM problems WHERE course_id = :c"
            " AND (CAST(:all AS boolean) OR archived_at IS NULL) ORDER BY id"
        ),
        {"c": course_id, "all": include_archived},
    ).mappings().all()
    concepts = _concepts(conn, [r["id"] for r in rows])
    return [Problem(**r, concepts=concepts[r["id"]]) for r in rows]


def get_problem(conn: Connection, problem_id: int) -> ProblemDetail | None:
    row = conn.execute(
        text(f"SELECT {PROBLEM_COLUMNS} FROM problems WHERE id = :id"), {"id": problem_id}
    ).mappings().first()
    if row is None:
        return None
    examples = conn.execute(
        text(
            "SELECT input, expected FROM test_cases"
            " WHERE problem_id = :id AND NOT hidden ORDER BY id"
        ),
        {"id": problem_id},
    ).mappings().all()
    return ProblemDetail(
        **row,
        concepts=_concepts(conn, [problem_id])[problem_id],
        examples=[dict(e) for e in examples],
    )


def save_problem(
    conn: Connection,
    *,
    course_id: int,
    title: str,
    statement: str,
    kind: str,
    difficulty_b: float,
    discrimination_a: float,
    param_source: str,
    reference_solution: str | None,
    concept_weights: list[tuple[int, float]],
    tests: list[dict],
    options: list[dict],
) -> tuple[int, Literal["created", "updated", "unchanged"]]:
    """Insert a problem, or replace the content of the one with the same title in the course.

    An identical problem is left alone, so importing the same bank again keeps its ids and any human review.
    """
    existing = conn.execute(
        text("SELECT id FROM problems WHERE course_id = :c AND title = :t"),
        {"c": course_id, "t": title},
    ).scalar()
    values = {
        "c": course_id, "t": title, "s": statement, "k": kind, "b": difficulty_b,
        "a": discrimination_a, "ps": param_source, "ref": reference_solution,
    }
    if existing is None:
        problem_id = conn.execute(
            text(
                "INSERT INTO problems (course_id, title, statement, kind, difficulty_b,"
                " discrimination_a, param_source, reference_solution)"
                " VALUES (:c, :t, :s, :k, :b, :a, :ps, :ref) RETURNING id"
            ),
            values,
        ).scalar_one()
    elif _same_content(conn, existing, values, concept_weights, tests, options):
        return existing, "unchanged"
    else:
        problem_id = existing
        conn.execute(
            text(
                "UPDATE problems SET statement = :s, kind = :k, difficulty_b = :b,"
                " discrimination_a = :a, param_source = :ps, reference_solution = :ref,"
                " review_status = 'needs human review' WHERE id = :id"
            ),
            {**values, "id": problem_id},
        )
        for table in ("test_cases", "problem_concepts", "item_options"):
            conn.execute(text(f"DELETE FROM {table} WHERE problem_id = :id"), {"id": problem_id})

    for concept_id, weight in concept_weights:
        conn.execute(
            text("INSERT INTO problem_concepts VALUES (:p, :c, :w)"),
            {"p": problem_id, "c": concept_id, "w": weight},
        )
    for t in tests:
        conn.execute(
            text(
                "INSERT INTO test_cases (problem_id, input, expected, hidden, category)"
                " VALUES (:p, :i, :e, :h, :c)"
            ),
            {
                "p": problem_id,
                "i": t["input"],
                "e": t["expected"],
                "h": t["hidden"],
                "c": t["category"],
            },
        )
    for o in options:
        conn.execute(
            text(
                "INSERT INTO item_options (problem_id, option_text, is_correct, misconception_id)"
                " VALUES (:p, :t, :ok, :m)"
            ),
            {"p": problem_id, "t": o["text"], "ok": o["correct"], "m": o["misconception_id"]},
        )
    return problem_id, "created" if existing is None else "updated"


def _same_content(
    conn: Connection, problem_id: int, values: dict, concept_weights: list, tests: list[dict], options: list[dict]
) -> bool:
    row = conn.execute(
        text(
            "SELECT statement, kind, difficulty_b, discrimination_a, param_source, reference_solution"
            " FROM problems WHERE id = :id"
        ),
        {"id": problem_id},
    ).one()
    if tuple(row) != (values["s"], values["k"], values["b"], values["a"], values["ps"], values["ref"]):
        return False
    stored_concepts = conn.execute(
        text("SELECT concept_id, weight FROM problem_concepts WHERE problem_id = :id"), {"id": problem_id}
    ).all()
    stored_tests = conn.execute(
        text("SELECT input, expected, hidden, category FROM test_cases WHERE problem_id = :id ORDER BY id"),
        {"id": problem_id},
    ).all()
    stored_options = conn.execute(
        text("SELECT option_text, is_correct, misconception_id FROM item_options WHERE problem_id = :id ORDER BY id"),
        {"id": problem_id},
    ).all()
    return (
        sorted(map(tuple, stored_concepts)) == sorted((c, w) for c, w in concept_weights)
        and [tuple(t) for t in stored_tests] == [(t["input"], t["expected"], t["hidden"], t["category"]) for t in tests]
        and [tuple(o) for o in stored_options] == [(o["text"], o["correct"], o["misconception_id"]) for o in options]
    )


def source(conn: Connection, problem_id: int) -> dict | None:
    """A coding problem as its editor needs it: hidden tests and the reference solution included (instructors only)."""
    row = conn.execute(
        text(
            "SELECT course_id, title, statement, difficulty_b, discrimination_a, reference_solution, param_source"
            " FROM problems"
            " WHERE id = :p AND kind = 'code'"
        ),
        {"p": problem_id},
    ).mappings().first()
    if row is None:
        return None
    concepts = conn.execute(
        text(
            "SELECT pc.concept_id, c.name, pc.weight FROM problem_concepts pc JOIN concepts c ON c.id = pc.concept_id"
            " WHERE pc.problem_id = :p ORDER BY c.name"
        ),
        {"p": problem_id},
    ).mappings().all()
    tests = conn.execute(
        text("SELECT input, expected, hidden, category FROM test_cases WHERE problem_id = :p ORDER BY id"),
        {"p": problem_id},
    ).mappings().all()
    return {**row, "reference_solution": row["reference_solution"] or "", "concepts": [dict(c) for c in concepts],
            "test_cases": [dict(t) for t in tests]}


def update_code_problem(
    conn: Connection, problem_id: int, *, title: str, statement: str, difficulty_b: float, discrimination_a: float,
    reference_solution: str, concept_weights: list[tuple[int, float]], tests: list[dict], param_source: str,
) -> None:
    """Replace a coding problem's content. It needs a fresh human review; past run results stay as they were."""
    conn.execute(
        text(
            "UPDATE problems SET title = :t, statement = :s, difficulty_b = :b, discrimination_a = :a,"
            " reference_solution = :ref, param_source = :ps, review_status = 'needs human review' WHERE id = :p"
        ),
        {"t": title, "s": statement, "b": difficulty_b, "a": discrimination_a, "ref": reference_solution,
         "ps": param_source, "p": problem_id},
    )
    for table in ("test_cases", "problem_concepts"):
        conn.execute(text(f"DELETE FROM {table} WHERE problem_id = :p"), {"p": problem_id})
    for concept_id, weight in concept_weights:
        conn.execute(text("INSERT INTO problem_concepts VALUES (:p, :c, :w)"),
                     {"p": problem_id, "c": concept_id, "w": weight})
    for t in tests:
        conn.execute(
            text("INSERT INTO test_cases (problem_id, input, expected, hidden, category) VALUES (:p, :i, :e, :h, :c)"),
            {"p": problem_id, "i": t["input"], "e": t["expected"], "h": t["hidden"], "c": t["category"]},
        )
