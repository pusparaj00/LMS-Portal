"""A small, clearly labelled SYNTHETIC class for the instructor dashboard (F-61).

Students are named synthetic-NN@synthetic.local, cannot log in (their password is random and discarded), and
their mastery is written only by the mastery service, as simulated placement answers.
The domain is reserved: nobody can register on it, so the "synthetic" label on the dashboard cannot be given to a
real student. app.seed calls this for the demo.

Usage: python -m app.synthetic --course-title "Python Fundamentals" --students 20
"""
import argparse
import re
import secrets

import numpy as np
from sqlalchemy import Connection, text

from app.auth import hash_password
from app.db import get_engine
from app.diagnostic.selection import EVIDENCE_TYPE, Item
from app.mastery import client as mastery
from simulation import model

SYNTHETIC_DOMAIN = "@synthetic.local"
SYNTHETIC_NAME = re.compile(r"synthetic-\d{2,}@synthetic\.local")
CODE_ITEMS_PER_STUDENT = 6
SEED = 2026


def is_synthetic(email: str) -> bool:
    return SYNTHETIC_NAME.fullmatch(email) is not None


def _items(conn: Connection, course_id: int) -> tuple[list[Item], list[int]]:
    concept_ids = list(
        conn.execute(text("SELECT id FROM concepts WHERE course_id = :c ORDER BY id"), {"c": course_id}).scalars()
    )
    index = {cid: i for i, cid in enumerate(concept_ids)}
    by_id: dict[int, dict] = {}
    for pid, kind, a, b, cid, weight in conn.execute(
        text(
            "SELECT p.id, p.kind, p.discrimination_a, p.difficulty_b, pc.concept_id, pc.weight FROM problems p"
            " JOIN problem_concepts pc ON pc.problem_id = p.id WHERE p.course_id = :c ORDER BY p.id"
        ),
        {"c": course_id},
    ):
        entry = by_id.setdefault(pid, {"kind": kind, "a": a, "b": b, "concepts": {}})
        entry["concepts"][index[cid]] = weight
    items = [Item(pid, e["kind"], e["a"], e["b"], e["concepts"]) for pid, e in sorted(by_id.items())]
    return items, concept_ids


def _user(conn: Connection, email: str) -> int:
    return conn.execute(
        text(
            "INSERT INTO users (email, password_hash, role) VALUES (:e, :h, 'student')"
            " ON CONFLICT (email) DO UPDATE SET email = excluded.email RETURNING id"
        ),
        {"e": email, "h": hash_password(secrets.token_urlsafe(32))},
    ).scalar_one()


def seed(course_id: int, students: int = 20, seed: int = SEED) -> dict:
    with get_engine().begin() as conn:
        items, concept_ids = _items(conn, course_id)
        if not items:
            raise SystemExit("the course has no problems; import the question bank first")
        wrong_options: dict[int, list[int]] = {}
        for pid, oid in conn.execute(
            text(
                "SELECT problem_id, id FROM item_options WHERE NOT is_correct AND problem_id IN"
                " (SELECT id FROM problems WHERE course_id = :c) ORDER BY id"
            ),
            {"c": course_id},
        ):
            wrong_options.setdefault(pid, []).append(oid)
        user_ids = []
        for n in range(1, students + 1):
            uid = _user(conn, f"synthetic-{n:02d}{SYNTHETIC_DOMAIN}")
            conn.execute(
                text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c) ON CONFLICT DO NOTHING"),
                {"u": uid, "c": course_id},
            )
            user_ids.append(uid)

    rng = np.random.default_rng(seed)
    theta = model.make_students(rng, students, len(concept_ids))
    a_true, b_true = model.true_item_params(rng, items)
    probabilities = model.response_probabilities(theta, items, a_true, b_true)
    code_items = [i for i in items if i.kind == "code"][:CODE_ITEMS_PER_STUDENT]
    asked = [i for i in items if i.kind == "mcq"] + code_items
    position = {item.id: n for n, item in enumerate(items)}

    recorded = 0
    for s, uid in enumerate(user_ids):
        for item in asked:
            correct = bool(rng.random() < probabilities[s, position[item.id]])
            wrong = wrong_options.get(item.id, [])
            option = None if correct or item.kind != "mcq" or not wrong else int(rng.choice(wrong))
            changes = mastery.record_answer(
                user_id=uid, problem_id=item.id, correct=correct, evidence_type=EVIDENCE_TYPE[item.kind],
                evidence_ref=f"synthetic:{s + 1}:{item.id}", option_id=option,
            )
            recorded += bool(changes)
    return {"students": students, "items_each": len(asked), "answers_applied": recorded}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-title", default="Python Fundamentals")
    parser.add_argument("--students", type=int, default=20)
    args = parser.parse_args()
    with get_engine().connect() as conn:
        course_id = conn.execute(
            text("SELECT id FROM courses WHERE title = :t ORDER BY id LIMIT 1"), {"t": args.course_title}
        ).scalar()
    if course_id is None:
        raise SystemExit(f"no course titled '{args.course_title}'")
    print(seed(course_id, args.students))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
