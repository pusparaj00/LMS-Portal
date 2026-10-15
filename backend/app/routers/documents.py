"""Course notes (F-40, TR-A-07): upload returns at once; embedding happens in the worker."""
import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.db import get_redis
from app.retrieval import pdf, store
from app.schemas import DocumentCreate, DocumentOut

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]


def _pdf_text(encoded: str) -> str:
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "pdf_base64 is not valid base64") from None
    try:
        return pdf.extract_text(data)
    except pdf.PdfError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("", response_model=DocumentOut, status_code=202)
def upload(course_id: int, body: DocumentCreate, user: Instructor, conn: Conn):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    concept_id = None
    if body.concept:
        concept_id = conn.execute(
            text("SELECT id FROM concepts WHERE course_id = :c AND name = :n"), {"c": course_id, "n": body.concept}
        ).scalar()
        if concept_id is None:
            raise HTTPException(422, f"unknown concept '{body.concept}'")
    notes = body.text if body.text is not None else _pdf_text(body.pdf_base64)
    document_id = store.save_document(
        conn, course_id=course_id, title=body.title, source_ref=body.source_ref or body.title,
        body=notes, concept_id=concept_id,
    )
    conn.commit()  # the worker reads the row, so it must exist before the job is queued
    get_redis().rpush(store.QUEUE, document_id)
    return DocumentOut(id=document_id, title=body.title, concept=body.concept, status="pending", detail=None)


@router.get("", response_model=list[DocumentOut])
def list_documents(course_id: int, user: Instructor, conn: Conn):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    rows = conn.execute(
        text(
            "SELECT d.id, d.title, c.name AS concept, d.status, d.status_detail AS detail"
            " FROM documents d LEFT JOIN concepts c ON c.id = d.concept_id WHERE d.course_id = :c ORDER BY d.id"
        ),
        {"c": course_id},
    ).mappings()
    return [DocumentOut(**r) for r in rows]
