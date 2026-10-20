"""Course-note storage, ingestion and retrieval in pgvector (TR-L-01, TR-L-02, TR-A-07)."""
import hashlib
from dataclasses import dataclass

from sqlalchemy import Connection, text

from app.feedback import leak
from app.retrieval import embedder
from app.retrieval.chunking import chunk_note

QUEUE = "ingest:queue"


@dataclass(frozen=True)
class Source:
    chunk_id: int
    title: str
    section: str
    text: str
    score: float
    concept_id: int | None


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def save_document(
    conn: Connection, *, course_id: int, title: str, source_ref: str, body: str, concept_id: int | None
) -> int:
    """Create or update the note and mark it pending; the worker embeds it later."""
    return conn.execute(
        text(
            "INSERT INTO documents (course_id, title, source_ref, body, concept_id, content_hash, status)"
            " VALUES (:c, :t, :s, :b, :k, :h, 'pending')"
            " ON CONFLICT (course_id, source_ref) DO UPDATE SET title = excluded.title, body = excluded.body,"
            " concept_id = excluded.concept_id, content_hash = excluded.content_hash, status = 'pending',"
            " status_detail = NULL RETURNING id"
        ),
        {
            "c": course_id, "t": title, "s": source_ref, "b": body, "k": concept_id,
            "h": hashlib.sha256(body.encode()).hexdigest(),
        },
    ).scalar_one()


def ingest_document(conn: Connection, document_id: int) -> int:
    """Chunk, embed and store one note. Safe to run again: chunks are replaced in one transaction."""
    row = conn.execute(
        text("SELECT title, body FROM documents WHERE id = :d FOR UPDATE"), {"d": document_id}
    ).first()
    if row is None:
        raise LookupError(f"document {document_id} does not exist")
    chunks = chunk_note(row.body)
    vectors = embedder.embed_passages([f"{row.title}: {c.section}\n{c.text}" for c in chunks])
    conn.execute(text("DELETE FROM chunks WHERE document_id = :d"), {"d": document_id})
    for chunk, vector in zip(chunks, vectors, strict=True):
        conn.execute(
            text(
                "INSERT INTO chunks (document_id, text, embedding, embedding_model, source_ref, chunk_index, section)"
                " VALUES (:d, :t, CAST(:v AS vector), :m, :r, :i, :s)"
            ),
            {
                "d": document_id, "t": chunk.text, "v": _vector(vector), "m": embedder.model_id(),
                "r": f"{row.title} > {chunk.section}" if chunk.section else row.title,
                "i": chunk.index, "s": chunk.section,
            },
        )
    conn.execute(
        text("UPDATE documents SET status = 'ready', status_detail = NULL WHERE id = :d"), {"d": document_id}
    )
    return len(chunks)


def search(
    conn: Connection, *, course_id: int, query: str, k: int = 3, min_score: float, concept_id: int | None = None
) -> list[Source]:
    """Top-k chunks above the minimum cosine similarity; an empty list means no course source applies."""
    vector = _vector(embedder.embed_query(query))
    rows = conn.execute(
        text(
            "SELECT c.id, d.title, c.section, c.text, d.concept_id,"
            " 1 - (c.embedding <=> CAST(:q AS vector)) AS score"
            " FROM chunks c JOIN documents d ON d.id = c.document_id"
            " WHERE d.course_id = :course AND d.status = 'ready' AND c.embedding_model = :m"
            " AND (CAST(:concept AS integer) IS NULL OR d.concept_id = :concept)"
            " ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": vector, "course": course_id, "m": embedder.model_id(), "concept": concept_id, "k": k},
    )
    return [
        Source(r.id, r.title, r.section or "", r.text, float(r.score), r.concept_id)
        for r in rows
        if r.score >= min_score
    ]


def problems_copied_by(conn: Connection, course_id: int, body: str) -> list[str]:
    """Titles of the course's problems whose reference solution the note's code copies (F-93): such a note would hand
    out a solution if it were shown to students."""
    rows = conn.execute(
        text("SELECT title, reference_solution FROM problems WHERE course_id = :c AND reference_solution IS NOT NULL"),
        {"c": course_id},
    ).all()
    return [title for title, reference in rows if leak.copies_reference(body, reference)]
