"""TR-L-01, TR-L-02, TR-A-07, TR-V-09: chunking, embedding, retrieval and the ingestion worker."""
import uuid

import pytest
import redis
from sqlalchemy import text

from app.db import get_redis
from app.retrieval import chunking, embedder, store
from app.worker import main as worker

LONG_NOTE = "---\ntitle: Long\nconcept: loops\n---\n## Section\n" + " ".join(f"word{i}" for i in range(300))


def test_a_note_splits_into_sections_that_keep_their_heading():
    fields, body = chunking.parse_note(
        "---\ntitle: Loops\nconcept: loops\nstatus: needs human review\n---\n## A\nfirst part\n\n## B\nsecond part\n"
    )
    assert fields == {"title": "Loops", "concept": "loops", "status": "needs human review"}
    chunks = chunking.chunk_note(body)
    assert [(c.section, c.text) for c in chunks] == [("A", "first part"), ("B", "second part")]


def test_long_sections_become_overlapping_chunks():
    _, body = chunking.parse_note(LONG_NOTE)
    chunks = chunking.chunk_note(body)
    assert len(chunks) == 3 and [c.index for c in chunks] == [0, 1, 2]
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert len(first) == chunking.CHUNK_WORDS
    assert first[-chunking.OVERLAP_WORDS :] == second[: chunking.OVERLAP_WORDS]
    assert all(c.section == "Section" for c in chunks)


@pytest.fixture(scope="module")
def notes_course(make_user, owner):
    instructor_id, _ = make_user("instructor")
    with owner.begin() as conn:
        course = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('Retrieval course', :i) RETURNING id"),
            {"i": instructor_id},
        ).scalar_one()
        concept = conn.execute(
            text("INSERT INTO concepts (course_id, name) VALUES (:c, 'loops') RETURNING id"), {"c": course}
        ).scalar_one()
        for title, body in {
            "Loops": "---\ntitle: Loops\n---\n## How range works\n`range(5)` counts from 0 up to but not including 5, so the last "
            "number is 4. To include n write `range(1, n + 1)`.\n\n## The while loop\nA while loop repeats as long as "
            "its condition is true and must change something that makes it stop.",
            "Strings": "---\ntitle: Strings\n---\n## Strings are immutable\nMethods such as upper() return a new string and leave the "
            "original unchanged, so assign the result back to keep it.",
        }.items():
            _, text_body = chunking.parse_note(body)
            document = store.save_document(
                conn, course_id=course, title=title, source_ref=f"{title}.md", body=text_body, concept_id=concept
            )
            store.ingest_document(conn, document)
    return {"course": course, "concept": concept}


def search(conn, course, query, **kw):
    return store.search(conn, course_id=course, query=query, min_score=kw.pop("min_score", 0.67), **kw)


def test_the_right_note_is_retrieved_and_stores_the_model_name_and_version(owner, notes_course):
    with owner.connect() as conn:
        hits = search(conn, notes_course["course"], "why does range stop before the last number")
        models = conn.execute(
            text("SELECT DISTINCT embedding_model FROM chunks c JOIN documents d ON d.id = c.document_id"
                 " WHERE d.course_id = :c"),
            {"c": notes_course["course"]},
        ).scalars().all()
    assert hits and (hits[0].title, hits[0].section) == ("Loops", "How range works")
    assert models == [embedder.model_id()] and "@fastembed-" in models[0]


def test_an_unrelated_question_returns_no_source(owner, notes_course):
    with owner.connect() as conn:
        assert search(conn, notes_course["course"], "what is the capital of France") == []
        assert search(conn, notes_course["course"], "how do I bake bread") == []


def test_retrieval_can_be_restricted_to_a_concept(owner, notes_course):
    with owner.connect() as conn:
        assert search(conn, notes_course["course"], "range", concept_id=notes_course["concept"], min_score=-1.0)
        assert search(conn, notes_course["course"], "range", concept_id=0, min_score=-1.0) == []


def test_vectors_from_another_embedding_model_are_ignored(owner, notes_course):
    with owner.begin() as conn:
        conn.execute(
            text("UPDATE chunks SET embedding_model = 'old-model' WHERE document_id IN"
                 " (SELECT id FROM documents WHERE course_id = :c)"),
            {"c": notes_course["course"]},
        )
    with owner.connect() as conn:
        assert search(conn, notes_course["course"], "range stops before the last number", min_score=-1.0) == []
    with owner.begin() as conn:
        for document in conn.execute(text("SELECT id FROM documents WHERE course_id = :c"), {"c": notes_course["course"]}):
            store.ingest_document(conn, document.id)  # re-embedding restores them
    with owner.connect() as conn:
        assert search(conn, notes_course["course"], "range stops before the last number")


def test_ingesting_twice_does_not_duplicate_chunks(owner, notes_course):
    def count(conn):
        return conn.execute(
            text("SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.course_id = :c"),
            {"c": notes_course["course"]},
        ).scalar_one()

    with owner.begin() as conn:
        before = count(conn)
        for document in conn.execute(text("SELECT id FROM documents WHERE course_id = :c"), {"c": notes_course["course"]}).all():
            store.ingest_document(conn, document.id)
        assert count(conn) == before


@pytest.fixture
def private_queues(monkeypatch):
    """Use queue names of our own so the running worker container never sees these jobs."""
    tag = uuid.uuid4().hex[:6]
    monkeypatch.setattr(store, "QUEUE", f"test:{tag}:queue")
    monkeypatch.setattr(worker, "PROCESSING", f"test:{tag}:processing")
    monkeypatch.setattr(worker, "FAILED", f"test:{tag}:failed")
    monkeypatch.setattr(worker, "ATTEMPTS", f"test:{tag}:attempts")
    r = get_redis()
    yield r
    r.delete(store.QUEUE, worker.PROCESSING, worker.FAILED, worker.ATTEMPTS)


def test_the_worker_embeds_a_queued_note_and_clears_the_job(owner, notes_course, private_queues):
    r: redis.Redis = private_queues
    with owner.begin() as conn:
        document = store.save_document(
            conn, course_id=notes_course["course"], title="Queued", source_ref="queued.md",
            body="## Only section\nSome words about loops.", concept_id=notes_course["concept"],
        )
    r.rpush(store.QUEUE, document)
    job = r.blmove(store.QUEUE, worker.PROCESSING, 1, "LEFT", "RIGHT")
    worker.process(r, owner, job)
    with owner.connect() as conn:
        status = conn.execute(text("SELECT status FROM documents WHERE id = :d"), {"d": document}).scalar_one()
    assert status == "ready" and r.llen(worker.PROCESSING) == 0 and r.llen(store.QUEUE) == 0


def test_a_failing_job_is_retried_then_marked_failed(owner, notes_course, private_queues):
    r: redis.Redis = private_queues
    with owner.begin() as conn:
        document = store.save_document(
            conn, course_id=notes_course["course"], title="Broken", source_ref="broken.md", body="x", concept_id=None
        )
    for attempt in range(1, worker.MAX_ATTEMPTS + 1):
        r.rpush(store.QUEUE, document)
        job = r.blmove(store.QUEUE, worker.PROCESSING, 1, "LEFT", "RIGHT")
        original = store.ingest_document
        store.ingest_document = lambda conn, d: (_ for _ in ()).throw(RuntimeError("model unavailable"))
        try:
            worker.process(r, owner, job)
        finally:
            store.ingest_document = original
        if attempt < worker.MAX_ATTEMPTS:
            assert r.llen(store.QUEUE) == 1  # put back for another try
            r.lpop(store.QUEUE)
    assert r.llen(worker.FAILED) == 1
    with owner.connect() as conn:
        row = conn.execute(text("SELECT status, status_detail FROM documents WHERE id = :d"), {"d": document}).one()
    assert row.status == "failed" and "model unavailable" in row.status_detail


def test_a_job_left_in_processing_by_a_dead_worker_is_run_again(private_queues):
    r: redis.Redis = private_queues
    r.rpush(worker.PROCESSING, 4242)
    assert worker.requeue_interrupted(r) == 1
    assert r.lrange(store.QUEUE, 0, -1) == [b"4242"] and r.llen(worker.PROCESSING) == 0
