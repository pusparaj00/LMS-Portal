"""Retrieval evaluation (TR-V-09) and relevance-threshold choice (TR-L-01).

Usage (from backend/, with the notes ingested): python -m evaluation.retrieval [--threshold-only]
The two question files are written before any run; the threshold set only chooses the threshold and
the 20 test questions only measure accuracy.
"""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.db import get_engine
from app.retrieval import embedder, store

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = next(p for p in (ROOT / "data" / "eval", ROOT.parent / "data" / "eval") if p.exists())
COURSE_TITLE = "Python Fundamentals"
TOP_K = 3


def course_id(conn) -> int:
    query = text("SELECT id FROM courses WHERE title = :t ORDER BY id LIMIT 1")
    return conn.execute(query, {"t": COURSE_TITLE}).scalar_one()


def best_score(conn, course: int, query: str) -> float:
    hits = store.search(conn, course_id=course, query=query, k=1, min_score=-1.0)
    return hits[0].score if hits else float("-inf")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-score", type=float, default=None, help="relevance threshold to apply to the test")
    args = parser.parse_args()
    threshold_set = json.loads((EVAL_DIR / "retrieval_threshold_set.json").read_text())
    questions = json.loads((EVAL_DIR / "retrieval_questions.json").read_text())

    with get_engine().connect() as conn:
        course = course_id(conn)
        on = sorted(best_score(conn, course, q) for q in threshold_set["on_topic"])
        off = sorted(best_score(conn, course, q) for q in threshold_set["off_topic"])
        print(f"on-topic best scores:  min {on[0]:.3f}  median {on[len(on) // 2]:.3f}  max {on[-1]:.3f}")
        print(f"off-topic best scores: min {off[0]:.3f}  median {off[len(off) // 2]:.3f}  max {off[-1]:.3f}")
        separable = on[0] > off[-1]
        suggested = round((on[0] + off[-1]) / 2, 2)
        print(f"separable: {separable}; midpoint between lowest on-topic and highest off-topic: {suggested}")
        threshold = args.min_score if args.min_score is not None else suggested

        top1 = top3 = 0
        misses = []
        for item in questions:
            hits = store.search(conn, course_id=course, query=item["question"], k=TOP_K, min_score=threshold)
            ranked = [(h.title, h.section) for h in hits]
            want = (item["note"], item["section"])
            top1 += bool(ranked) and ranked[0] == want
            if want in ranked:
                top3 += 1
            else:
                misses.append((item["question"], ranked[:1], want))
        total = len(questions)
        print(f"\nthreshold applied: {threshold}")
        print(f"right chunk in the top {TOP_K}: {top3}/{total} = {top3 / total:.0%}")
        print(f"right chunk first: {top1}/{total} = {top1 / total:.0%}")
        for question, got, want in misses:
            print(f"  MISS: {question!r} wanted {want}, got {got}")
    print(f"model: {embedder.model_id()}   run: {datetime.now(UTC):%Y-%m-%d %H:%M UTC}")


if __name__ == "__main__":
    main()
