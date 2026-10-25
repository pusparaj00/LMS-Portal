import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text

from app import audit, ratelimit
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.concept_graph import creates_cycle
from app.schemas import (
    ConceptCreate,
    Course,
    CourseConcept,
    CourseCreate,
    CourseUpdate,
    JoinCode,
    JoinCodeEnabled,
    JoinIn,
    PrerequisitesUpdate,
)

router = APIRouter(prefix="/courses", tags=["courses"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]


_COURSE = "c.id, c.title, c.instructor_id, c.section, c.subject, c.color, c.archived_at IS NOT NULL AS archived"
_ENROLLED = "EXISTS (SELECT 1 FROM enrollments e WHERE e.course_id = c.id AND e.user_id = :u)"


@router.get("", response_model=list[Course])
def list_courses(user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    """A student sees the courses they have joined, a teacher the courses they teach (archived ones too, so they can be
    restored), an admin every live course. Nobody can browse courses they have no part in: joining takes a code."""
    if user.role == "student":
        where = f"{_ENROLLED} AND c.archived_at IS NULL"
    elif user.role == "instructor":
        where = "EXISTS (SELECT 1 FROM course_teachers t WHERE t.course_id = c.id AND t.user_id = :u)"
    else:
        where = "c.archived_at IS NULL"
    rows = conn.execute(
        text(f"SELECT {_COURSE}, {_ENROLLED} AS enrolled FROM courses c WHERE {where} ORDER BY c.id"),
        {"u": user.id},
    ).mappings()
    return [dict(r) for r in rows]


@router.post("", response_model=Course, status_code=201)
def create_course(
    body: CourseCreate,
    user: Annotated[CurrentUser, Depends(require_role("instructor"))],
    conn: Conn,
):
    row = conn.execute(
        text(
            "INSERT INTO courses (title, instructor_id) VALUES (:t, :u)"
            " RETURNING id, title, instructor_id, section, subject, color, false AS archived"
        ),
        {"t": body.title, "u": user.id},
    ).mappings().one()
    return {**row, "enrolled": False}


def _normal_code(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", raw).upper()


@router.post("/join", response_model=Course)
def join_course(body: JoinIn, user: Annotated[CurrentUser, Depends(require_role("student"))], conn: Conn):
    """Joins the course that has this class code. An unknown, disabled or archived code all get the same answer, and
    the number of tries is limited, so codes cannot be guessed."""
    ratelimit.check("join", user.id)
    row = conn.execute(
        text(
            f"SELECT {_COURSE} FROM courses c WHERE c.join_code = :code AND c.join_enabled AND c.archived_at IS NULL"
        ),
        {"code": _normal_code(body.code)},
    ).mappings().first()
    if row is None:
        audit.record("course.join_refused", user_id=user.id, status=404)
        raise HTTPException(404, "that class code does not match a course that is open to new students")
    conn.execute(
        text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c) ON CONFLICT DO NOTHING"),
        {"u": user.id, "c": row["id"]},
    )
    audit.record("course.joined", user_id=user.id, status=200, detail={"course_id": row["id"]}, conn=conn)
    return {**row, "enrolled": True}


def _code_out(conn, course_id: int) -> JoinCode:
    row = conn.execute(
        text("SELECT join_code, join_enabled FROM courses WHERE id = :c"), {"c": course_id}
    ).first()
    if row is None:
        raise HTTPException(404, "course not found")
    return JoinCode(code=row.join_code, enabled=row.join_enabled, link=f"#/join/{row.join_code}")


@router.get("/{course_id}/join-code", response_model=JoinCode)
def read_join_code(
    course_id: int, user: Annotated[CurrentUser, Depends(require_role("instructor", "admin"))], conn: Conn
):
    _own(conn, user, course_id)
    return _code_out(conn, course_id)


@router.post("/{course_id}/join-code/reset", response_model=JoinCode)
def reset_join_code(course_id: int, user: Instructor, conn: Conn):
    """A new code at once; the old one and any link made from it stop working. Students already in stay in."""
    _own(conn, user, course_id)
    conn.execute(
        text("UPDATE courses SET join_code = :code WHERE id = :c"),
        {"code": secrets.token_hex(5).upper(), "c": course_id},
    )
    audit.record("course.join_code_reset", user_id=user.id, status=200, detail={"course_id": course_id}, conn=conn)
    return _code_out(conn, course_id)


@router.put("/{course_id}/join-code", response_model=JoinCode)
def set_join_code_enabled(course_id: int, body: JoinCodeEnabled, user: Instructor, conn: Conn):
    """Closing a class to new students without losing the code."""
    _own(conn, user, course_id)
    conn.execute(text("UPDATE courses SET join_enabled = :e WHERE id = :c"), {"e": body.enabled, "c": course_id})
    audit.record("course.join_code_enabled", user_id=user.id, status=200, conn=conn,
                 detail={"course_id": course_id, "enabled": body.enabled})
    return _code_out(conn, course_id)


@router.get("/{course_id}/concepts", response_model=list[CourseConcept])
def list_concepts(course_id: int, user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    """The concepts problems and notes can be tagged with (F-02)."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")
    rows = conn.execute(
        text(
            "SELECT id AS concept_id, name, parent_ids AS prerequisite_ids FROM concepts"
            " WHERE course_id = :c ORDER BY id"
        ),
        {"c": course_id},
    ).mappings()
    return [dict(r) for r in rows]


CONCEPT_NAME = re.compile(r"[a-z][a-z0-9_]+")


def _concept_name(raw: str) -> str:
    name = re.sub(r"[\s-]+", "_", raw.strip().lower())
    if not CONCEPT_NAME.fullmatch(name):
        raise HTTPException(
            422, "a concept name starts with a letter and uses only letters, digits, spaces and underscores"
        )
    return name


@router.post("/{course_id}/concepts", response_model=CourseConcept, status_code=201)
def create_concept(
    course_id: int, body: ConceptCreate, user: Annotated[CurrentUser, Depends(require_role("instructor"))], conn: Conn
):
    """Add a concept to the course's list (F-02). Mastery starts at the population prior and uses the default
    slip and guess rates until an instructor tunes them, so nothing else has to be set up."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    name = _concept_name(body.name)
    row = conn.execute(
        text(
            "INSERT INTO concepts (course_id, name) VALUES (:c, :n) ON CONFLICT (course_id, name) DO NOTHING"
            " RETURNING id AS concept_id, name"
        ),
        {"c": course_id, "n": name},
    ).mappings().first()
    if row is None:
        raise HTTPException(409, f"the concept '{name}' already exists in this course")
    return dict(row)



def _own(conn, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")


def _owner(conn, user: CurrentUser, course_id: int) -> None:
    """Archiving a course is for the teacher who owns it, not for a co-teacher."""
    if conn.execute(
        text("SELECT 1 FROM courses WHERE id = :c AND instructor_id = :u"), {"c": course_id, "u": user.id}
    ).first() is None:
        raise HTTPException(403, "only the course's owner can do that")


def _course(conn, user: CurrentUser, course_id: int) -> Course:
    row = conn.execute(
        text(f"SELECT {_COURSE}, false AS enrolled FROM courses c WHERE c.id = :c"), {"c": course_id}
    ).mappings().one()
    return Course(**row)


@router.patch("/{course_id}", response_model=Course)
def update_course(course_id: int, body: CourseUpdate, user: Instructor, conn: Conn):
    """Rename the course or set its section, subject and colour (F-83)."""
    _own(conn, user, course_id)
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    sets = ", ".join(f"{name} = :{name}" for name in changes)
    conn.execute(text(f"UPDATE courses SET {sets} WHERE id = :c"), {**changes, "c": course_id})
    return _course(conn, user, course_id)


@router.post("/{course_id}/archive", response_model=Course)
def archive_course(course_id: int, user: Instructor, conn: Conn):
    """Hidden from the course list and closed to new students; everything in it is kept and can be restored."""
    _owner(conn, user, course_id)
    conn.execute(text("UPDATE courses SET archived_at = COALESCE(archived_at, now()) WHERE id = :c"), {"c": course_id})
    return _course(conn, user, course_id)


@router.post("/{course_id}/restore", response_model=Course)
def restore_course(course_id: int, user: Instructor, conn: Conn):
    _owner(conn, user, course_id)
    conn.execute(text("UPDATE courses SET archived_at = NULL WHERE id = :c"), {"c": course_id})
    return _course(conn, user, course_id)


def _concept(conn, course_id: int, concept_id: int) -> None:
    if conn.execute(
        text("SELECT 1 FROM concepts WHERE id = :k AND course_id = :c"), {"k": concept_id, "c": course_id}
    ).first() is None:
        raise HTTPException(404, "concept not found")


@router.patch("/{course_id}/concepts/{concept_id}", response_model=CourseConcept)
def rename_concept(course_id: int, concept_id: int, body: ConceptCreate, user: Instructor, conn: Conn):
    """Renaming keeps every tag and the whole mastery history, which follow the concept, not its name."""
    _own(conn, user, course_id)
    _concept(conn, course_id, concept_id)
    name = _concept_name(body.name)
    clash = conn.execute(
        text("SELECT 1 FROM concepts WHERE course_id = :c AND name = :n AND id <> :k"),
        {"c": course_id, "n": name, "k": concept_id},
    ).first()
    if clash:
        raise HTTPException(409, f"the concept '{name}' already exists in this course")
    prerequisites = conn.execute(
        text("UPDATE concepts SET name = :n WHERE id = :k RETURNING parent_ids"), {"n": name, "k": concept_id}
    ).scalar_one()
    return CourseConcept(concept_id=concept_id, name=name, prerequisite_ids=prerequisites)


@router.put("/{course_id}/concepts/{concept_id}/prerequisites", response_model=CourseConcept)
def set_prerequisites(course_id: int, concept_id: int, body: PrerequisitesUpdate, user: Instructor, conn: Conn):
    """The concepts this one builds on (F-29). The first recommendation revises a weak one before this concept, and a
    sharp drop here is passed back to them. A concept cannot, even indirectly, be its own prerequisite."""
    _own(conn, user, course_id)
    _concept(conn, course_id, concept_id)
    wanted = list(dict.fromkeys(body.prerequisite_ids))
    rows = conn.execute(  # locked, so two teachers editing at once cannot together create a circle
        text("SELECT id, name, parent_ids FROM concepts WHERE course_id = :c FOR UPDATE"), {"c": course_id}
    ).all()
    known = {r.id: r for r in rows}
    unknown = [k for k in wanted if k not in known]
    if unknown:
        raise HTTPException(422, "a prerequisite must be a concept of this course")
    if concept_id in wanted:
        raise HTTPException(422, "a concept cannot be its own prerequisite")
    if creates_cycle({r.id: list(r.parent_ids) for r in rows}, concept_id, wanted):
        raise HTTPException(409, "that would make the concepts depend on each other in a circle")
    conn.execute(text("UPDATE concepts SET parent_ids = :p WHERE id = :k"), {"p": wanted, "k": concept_id})
    audit.record("concept.prerequisites", user_id=user.id, status=200, conn=conn,
                 detail={"course_id": course_id, "concept_id": concept_id, "prerequisite_ids": wanted})
    return CourseConcept(concept_id=concept_id, name=known[concept_id].name, prerequisite_ids=wanted)


# Every table with a foreign key to concepts; a row in any of them blocks deleting it.
_CONCEPT_USES = {
    "problems": "SELECT count(*) FROM problem_concepts WHERE concept_id = :k",
    "course notes": "SELECT count(*) FROM documents WHERE concept_id = :k",
    "misconceptions": "SELECT count(*) FROM misconceptions WHERE concept_id = :k",
    "students' mastery history": "SELECT count(*) FROM mastery_events WHERE concept_id = :k",
    "students' mastery": "SELECT count(*) FROM mastery WHERE concept_id = :k",
    "tuned rates": "SELECT count(*) FROM mastery_params WHERE concept_id = :k",
    "evidence links": "SELECT count(*) FROM evidence_concept_map WHERE concept_id = :k",
    "students' chat questions": "SELECT count(*) FROM chat_messages WHERE concept_id = :k",
}


@router.delete("/{course_id}/concepts/{concept_id}", status_code=204)
def delete_concept(course_id: int, concept_id: int, user: Instructor, conn: Conn):
    """Only an unused concept can be deleted; one in use can be renamed instead."""
    _own(conn, user, course_id)
    _concept(conn, course_id, concept_id)
    used = [what for what, sql in _CONCEPT_USES.items() if conn.execute(text(sql), {"k": concept_id}).scalar()]
    if used:
        raise HTTPException(409, f"this concept is still used by {', '.join(used)}; rename it instead")
    conn.execute(text("UPDATE concepts SET parent_ids = array_remove(parent_ids, :k) WHERE course_id = :c"),
                 {"k": concept_id, "c": course_id})
    conn.execute(text("DELETE FROM concepts WHERE id = :k"), {"k": concept_id})
    return Response(status_code=204)


@router.delete("/{course_id}/enroll", status_code=204)
def leave_course(course_id: int, user: Annotated[CurrentUser, Depends(require_role("student"))], conn: Conn):
    """The student leaves; their work and mastery history stay (deleting data is the erasure request)."""
    conn.execute(text("DELETE FROM enrollments WHERE course_id = :c AND user_id = :u"), {"c": course_id, "u": user.id})
    return Response(status_code=204)


@router.delete("/{course_id}/students/{student_id}", status_code=204)
def remove_student(course_id: int, student_id: int, user: Instructor, conn: Conn):
    """The teacher removes a student from the course; their work and history stay."""
    _own(conn, user, course_id)
    removed = conn.execute(
        text("DELETE FROM enrollments WHERE course_id = :c AND user_id = :u RETURNING 1"),
        {"c": course_id, "u": student_id},
    ).first()
    if removed is None:
        raise HTTPException(404, "that student is not enrolled in this course")
    return Response(status_code=204)
