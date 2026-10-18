"""Course content (F-66, F-67, F-68): ordered modules of lesson items, each student's completions.

Only the course's instructor edits. Students see published modules and published items of courses they are enrolled in.
Items are text, links or PDF files; the page shows text as text and a link as a link, so nothing here can run script.
"""
import base64
import binascii
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import ContentOut, ItemIn, ItemOut, ItemUpdate, ModuleIn, ModuleOut, ModuleUpdate, Move

router = APIRouter(prefix="/courses/{course_id}", tags=["content"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Student = Annotated[CurrentUser, Depends(require_role("student"))]
Member = Annotated[CurrentUser, Depends(current_user)]
MAX_PDF_BYTES = 4_500_000
PDF_START = b"%PDF-"
UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")


def _check(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


def _module(conn: Connection, course_id: int, module_id: int):
    row = conn.execute(
        text("SELECT id, published FROM modules WHERE id = :m AND course_id = :c"), {"m": module_id, "c": course_id}
    ).first()
    if row is None:
        raise HTTPException(404, "module not found")
    return row


def _item(conn: Connection, course_id: int, item_id: int):
    row = conn.execute(
        text(
            "SELECT i.id, i.module_id, i.kind, i.title, i.file_name, i.published, m.published AS module_published"
            " FROM content_items i JOIN modules m ON m.id = i.module_id WHERE i.id = :i AND m.course_id = :c"
        ),
        {"i": item_id, "c": course_id},
    ).first()
    if row is None:
        raise HTTPException(404, "item not found")
    return row


def _visible_to_student(item) -> bool:
    return item.published and item.module_published


def _move(conn: Connection, table: str, scope_column: str, scope_id: int, row_id: int, direction: str) -> None:
    """Swap with the neighbour; positions are then rewritten 0..n-1, so they stay tidy whatever happened before."""
    ids = list(conn.execute(
        text(f"SELECT id FROM {table} WHERE {scope_column} = :s ORDER BY position, id"), {"s": scope_id}
    ).scalars())
    at = ids.index(row_id)
    to = at - 1 if direction == "up" else at + 1
    if 0 <= to < len(ids):
        ids[at], ids[to] = ids[to], ids[at]
    for position, found in enumerate(ids):
        conn.execute(text(f"UPDATE {table} SET position = :p WHERE id = :i"), {"p": position, "i": found})


def _next_position(conn: Connection, table: str, scope_column: str, scope_id: int) -> int:
    return conn.execute(
        text(f"SELECT COALESCE(max(position) + 1, 0) FROM {table} WHERE {scope_column} = :s"), {"s": scope_id}
    ).scalar_one()


@router.get("/content", response_model=ContentOut)
def read_content(course_id: int, user: Member, conn: Conn):
    """A student gets the published modules and items with their own completions; staff get everything."""
    _check(conn, user, course_id)
    student = user.role == "student"
    modules = conn.execute(
        text(
            "SELECT id, title, published FROM modules WHERE course_id = :c"
            f"{' AND published' if student else ''} ORDER BY position, id"
        ),
        {"c": course_id},
    ).all()
    rows = conn.execute(
        text(
            "SELECT i.id, i.module_id, i.kind, i.title, i.body, i.url, i.file_name,"
            " octet_length(i.file_data) AS file_size, i.published, (c.user_id IS NOT NULL) AS completed"
            " FROM content_items i JOIN modules m ON m.id = i.module_id"
            " LEFT JOIN item_completions c ON c.item_id = i.id AND c.user_id = :u"
            f" WHERE m.course_id = :c{' AND i.published' if student else ''} ORDER BY i.position, i.id"
        ),
        {"c": course_id, "u": user.id},
    ).mappings().all()
    by_module: dict[int, list[ItemOut]] = {m.id: [] for m in modules}
    for r in rows:
        if r["module_id"] in by_module:
            by_module[r["module_id"]].append(ItemOut(
                id=r["id"], kind=r["kind"], title=r["title"], body=r["body"], url=r["url"], file_name=r["file_name"],
                file_size=r["file_size"], published=r["published"], completed=r["completed"] if student else None,
            ))
    rates = {} if student else _completion_rates(conn, course_id)
    out = [
        ModuleOut(
            id=m.id, title=m.title, published=m.published, items=by_module[m.id], total=len(by_module[m.id]),
            completed=sum(bool(i.completed) for i in by_module[m.id]) if student else None,
            completion_rate=rates.get(m.id),
        )
        for m in modules
    ]
    return ContentOut(
        modules=out, total=sum(m.total for m in out), completed=sum(m.completed or 0 for m in out) if student else None
    )


def _completion_rates(conn: Connection, course_id: int) -> dict[int, float]:
    """Per module: completions by enrolled students over what the class could have completed (published items)."""
    students = conn.execute(
        text("SELECT count(*) FROM enrollments e JOIN users u ON u.id = e.user_id"
             " WHERE e.course_id = :c AND u.role = 'student'"), {"c": course_id},
    ).scalar_one()
    if students == 0:
        return {}
    rows = conn.execute(
        text(
            "SELECT m.id, count(DISTINCT i.id) AS items,"
            " (SELECT count(*) FROM item_completions c JOIN content_items ci ON ci.id = c.item_id"
            "  JOIN enrollments e ON e.user_id = c.user_id AND e.course_id = :c"
            "  JOIN users u ON u.id = e.user_id AND u.role = 'student'"
            "  WHERE ci.module_id = m.id AND ci.published) AS done"
            " FROM modules m LEFT JOIN content_items i ON i.module_id = m.id AND i.published"
            " WHERE m.course_id = :c GROUP BY m.id"
        ),
        {"c": course_id},
    )
    return {r.id: round(r.done / (r.items * students) * 100, 1) for r in rows if r.items}


@router.post("/modules", response_model=ModuleOut, status_code=201)
def create_module(course_id: int, body: ModuleIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    row = conn.execute(
        text("INSERT INTO modules (course_id, title, position) VALUES (:c, :t, :p) RETURNING id, title, published"),
        {"c": course_id, "t": body.title.strip(), "p": _next_position(conn, "modules", "course_id", course_id)},
    ).one()
    return ModuleOut(id=row.id, title=row.title, published=row.published, items=[], total=0)


@router.patch("/modules/{module_id}", response_model=ModuleOut)
def update_module(course_id: int, module_id: int, body: ModuleUpdate, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _module(conn, course_id, module_id)
    conn.execute(
        text("UPDATE modules SET title = COALESCE(:t, title), published = COALESCE(:p, published) WHERE id = :m"),
        {"t": body.title.strip() if body.title else None, "p": body.published, "m": module_id},
    )
    return next(m for m in read_content(course_id, user, conn).modules if m.id == module_id)


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(course_id: int, module_id: int, user: Instructor, conn: Conn):
    """Removes the module, its items and every student's completions of them."""
    _check(conn, user, course_id)
    _module(conn, course_id, module_id)
    conn.execute(
        text("DELETE FROM item_completions WHERE item_id IN (SELECT id FROM content_items WHERE module_id = :m)"),
        {"m": module_id},
    )
    conn.execute(text("DELETE FROM content_items WHERE module_id = :m"), {"m": module_id})
    conn.execute(text("DELETE FROM modules WHERE id = :m"), {"m": module_id})
    return Response(status_code=204)


@router.post("/modules/{module_id}/move", status_code=204)
def move_module(course_id: int, module_id: int, body: Move, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _module(conn, course_id, module_id)
    _move(conn, "modules", "course_id", course_id, module_id, body.direction)
    return Response(status_code=204)


def _pdf_bytes(encoded: str) -> bytes:
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "pdf_base64 is not valid base64") from None
    if not data.startswith(PDF_START):
        raise HTTPException(422, "the file is not a PDF")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(422, "the PDF is larger than 4.5 MB")
    return data


def _pdf_name(name: str) -> str:
    cleaned = UNSAFE_NAME.sub("_", name).strip(" .") or "file"
    return cleaned if cleaned.lower().endswith(".pdf") else f"{cleaned}.pdf"


@router.post("/modules/{module_id}/items", response_model=ItemOut, status_code=201)
def create_item(course_id: int, module_id: int, body: ItemIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _module(conn, course_id, module_id)
    data = _pdf_bytes(body.pdf_base64) if body.kind == "file" else None
    row = conn.execute(
        text(
            "INSERT INTO content_items (module_id, kind, title, body, url, file_name, file_data, position, published)"
            " VALUES (:m, :k, :t, :b, :u, :fn, :fd, :p, :pub)"
            " RETURNING id, kind, title, body, url, file_name, octet_length(file_data) AS file_size, published"
        ),
        {
            "m": module_id, "k": body.kind, "t": body.title.strip(), "b": body.body, "u": body.url,
            "fn": _pdf_name(body.file_name) if body.file_name else None, "fd": data,
            "p": _next_position(conn, "content_items", "module_id", module_id), "pub": body.published,
        },
    ).mappings().one()
    return ItemOut(**row)


@router.patch("/items/{item_id}", response_model=ItemOut)
def update_item(course_id: int, item_id: int, body: ItemUpdate, user: Instructor, conn: Conn):
    """Text and link items change in place; a file is replaced by deleting it and adding another."""
    _check(conn, user, course_id)
    item = _item(conn, course_id, item_id)
    if (body.body is not None and item.kind != "text") or (body.url is not None and item.kind not in ("link", "video")):
        raise HTTPException(422, f"a {item.kind} item has no such field to change")
    row = conn.execute(
        text(
            "UPDATE content_items SET title = COALESCE(:t, title), body = COALESCE(:b, body), url = COALESCE(:u, url),"
            " published = COALESCE(:p, published) WHERE id = :i"
            " RETURNING id, kind, title, body, url, file_name, octet_length(file_data) AS file_size, published"
        ),
        {"t": body.title.strip() if body.title else None, "b": body.body, "u": body.url, "p": body.published,
         "i": item_id},
    ).mappings().one()
    return ItemOut(**row)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(course_id: int, item_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _item(conn, course_id, item_id)
    conn.execute(text("DELETE FROM item_completions WHERE item_id = :i"), {"i": item_id})
    conn.execute(text("DELETE FROM content_items WHERE id = :i"), {"i": item_id})
    return Response(status_code=204)


@router.post("/items/{item_id}/move", status_code=204)
def move_item(course_id: int, item_id: int, body: Move, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    item = _item(conn, course_id, item_id)
    _move(conn, "content_items", "module_id", item.module_id, item_id, body.direction)
    return Response(status_code=204)


@router.get("/items/{item_id}/file")
def download_file(course_id: int, item_id: int, user: Member, conn: Conn):
    """The PDF as an attachment, so the browser saves it instead of rendering it inside this site."""
    _check(conn, user, course_id)
    item = _item(conn, course_id, item_id)
    if item.kind != "file" or (user.role == "student" and not _visible_to_student(item)):
        raise HTTPException(404, "item not found")
    data = conn.execute(text("SELECT file_data FROM content_items WHERE id = :i"), {"i": item_id}).scalar_one()
    return Response(
        content=bytes(data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_pdf_name(item.file_name)}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.put("/items/{item_id}/completion", status_code=204)
def complete(course_id: int, item_id: int, user: Student, conn: Conn):
    _check(conn, user, course_id)
    item = _item(conn, course_id, item_id)
    if not _visible_to_student(item):
        raise HTTPException(404, "item not found")
    conn.execute(
        text("INSERT INTO item_completions (user_id, item_id) VALUES (:u, :i) ON CONFLICT DO NOTHING"),
        {"u": user.id, "i": item_id},
    )
    return Response(status_code=204)


@router.delete("/items/{item_id}/completion", status_code=204)
def uncomplete(course_id: int, item_id: int, user: Student, conn: Conn):
    _check(conn, user, course_id)
    _item(conn, course_id, item_id)
    conn.execute(
        text("DELETE FROM item_completions WHERE user_id = :u AND item_id = :i"), {"u": user.id, "i": item_id}
    )
    return Response(status_code=204)
