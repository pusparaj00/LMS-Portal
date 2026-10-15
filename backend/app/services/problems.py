from sqlalchemy import Connection, text

from app.schemas import ConceptTag, Problem, ProblemDetail

PROBLEM_COLUMNS = (
    "id, course_id, title, statement, language, kind, difficulty_b, discrimination_a, review_status"
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


def list_problems(conn: Connection, course_id: int) -> list[Problem]:
    rows = conn.execute(
        text(f"SELECT {PROBLEM_COLUMNS} FROM problems WHERE course_id = :c ORDER BY id"),
        {"c": course_id},
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
) -> tuple[int, bool]:
    """Insert a problem, or replace the content of the one with the same title in the course."""
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
    return problem_id, existing is None
