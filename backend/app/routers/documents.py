"""Course notes (F-40, TR-A-07): upload returns at once; embedding happens in the worker."""
import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text

from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.db import get_redis
from app.retrieval import pdf, store
from app.schemas import DocumentCreate, DocumentOut, NoteVisibility, StudentNoteBody, StudentNoteOut

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])
student_router = APIRouter(prefix="/courses/{course_id}/notes", tags=["documents"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Learner = Annotated[CurrentUser, Depends(require_role("student", "instructor"))]


def _set_visible(conn, document_id: int, visible: bool) -> None:
    conn.execute(text("UPDATE documents SET visible_to_students = :v WHERE id = :d"), {"v": visible, "d": document_id})


def _refuse_solution(conn, course_id: int, body: str, confirmed: bool) -> None:
    """F-93: a note whose code copies a problem's reference solution is shown only after a second, explicit go."""
    copied = [] if confirmed else store.problems_copied_by(conn, course_id, body)
    if copied:
        names = ", ".join(copied)
        raise HTTPException(409, f"these notes contain the solution to: {names}. Remove the code, or confirm.")


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
    if body.visible_to_students:
        _refuse_solution(conn, course_id, notes, body.confirm_solution)
    document_id = store.save_document(
        conn, course_id=course_id, title=body.title, source_ref=body.source_ref or body.title,
        body=notes, concept_id=concept_id,
    )
    _set_visible(conn, document_id, body.visible_to_students)
    conn.commit()  # the worker reads the row, so it must exist before the job is queued
    get_redis().rpush(store.QUEUE, document_id)
    return DocumentOut(
        id=document_id, title=body.title, concept=body.concept, status="pending", detail=None,
        visible_to_students=body.visible_to_students,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(course_id: int, user: Instructor, conn: Conn):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    rows = conn.execute(
        text(
            "SELECT d.id, d.title, c.name AS concept, d.status, d.status_detail AS detail, d.visible_to_students"
            " FROM documents d LEFT JOIN concepts c ON c.id = d.concept_id WHERE d.course_id = :c ORDER BY d.id"
        ),
        {"c": course_id},
    ).mappings()
    return [DocumentOut(**r) for r in rows]


@router.delete("/{document_id}", status_code=204)
def delete_document(course_id: int, document_id: int, user: Instructor, conn: Conn):
    """Removes the notes and their search chunks; a stored explanation that cited them is checked again before use."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    found = conn.execute(
        text("SELECT 1 FROM documents WHERE id = :d AND course_id = :c"), {"d": document_id, "c": course_id}
    ).first()
    if found is None:
        raise HTTPException(404, "notes not found")
    conn.execute(text("DELETE FROM chunks WHERE document_id = :d"), {"d": document_id})
    conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": document_id})
    return Response(status_code=204)


@router.patch("/{document_id}", response_model=DocumentOut)
def set_visibility(course_id: int, document_id: int, body: NoteVisibility, user: Instructor, conn: Conn):
    """Show a note to the course's students, or hide it again. The assistant uses the note either way."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    row = conn.execute(
        text("SELECT body FROM documents WHERE id = :d AND course_id = :c"), {"d": document_id, "c": course_id}
    ).first()
    if row is None:
        raise HTTPException(404, "notes not found")
    if body.visible_to_students:
        _refuse_solution(conn, course_id, row.body, body.confirm_solution)
    _set_visible(conn, document_id, body.visible_to_students)
    out = conn.execute(
        text(
            "SELECT d.id, d.title, c.name AS concept, d.status, d.status_detail AS detail, d.visible_to_students"
            " FROM documents d LEFT JOIN concepts c ON c.id = d.concept_id WHERE d.id = :d"
        ),
        {"d": document_id},
    ).mappings().one()
    return DocumentOut(**out)


def _visible_filter(user: CurrentUser) -> str:
    return "" if user.role != "student" else " AND d.visible_to_students"


@student_router.get("", response_model=list[StudentNoteOut])
def list_visible_notes(course_id: int, user: Learner, conn: Conn):
    """F-93: the notes a student may read. A teacher sees the same list (every note) to check what students see."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    rows = conn.execute(
        text(
            "SELECT d.id, d.title, c.name AS concept FROM documents d LEFT JOIN concepts c ON c.id = d.concept_id"
            f" WHERE d.course_id = :c{_visible_filter(user)} ORDER BY c.name NULLS LAST, d.title"
        ),
        {"c": course_id},
    ).mappings()
    return [StudentNoteOut(**r) for r in rows]


@student_router.get("/{document_id}", response_model=StudentNoteBody)
def read_note(course_id: int, document_id: int, user: Learner, conn: Conn):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    row = conn.execute(
        text(
            "SELECT d.id, d.title, c.name AS concept, d.body AS text FROM documents d"
            f" LEFT JOIN concepts c ON c.id = d.concept_id WHERE d.id = :d AND d.course_id = :c{_visible_filter(user)}"
        ),
        {"d": document_id, "c": course_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(404, "notes not found")
    return StudentNoteBody(**row)
