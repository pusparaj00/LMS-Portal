"""F-93: notes the instructor shows to students; a hidden note, or a note that copies a solution, never reaches them."""
from sqlalchemy import text

from tests.test_feedback_api import Q_REFERENCE, FakeLLM, llm, new_student, world  # noqa: F401  (fixtures)

API = "/api/v1"
FENCE = "`" * 3
SOLUTION_NOTE = f"## Worked example\n{FENCE}python\n{Q_REFERENCE}{FENCE}\nThis adds up a list."


def first_note(client, world):
    notes = client.get(f"{API}/courses/{world['course']}/documents", headers=world["instructor"]).json()
    return next(n for n in notes if n["title"] == "Loops")


def switch(client, world, document_id, visible, **extra):
    return client.patch(
        f"{API}/courses/{world['course']}/documents/{document_id}", headers=world["instructor"],
        json={"visible_to_students": visible, **extra},
    )


def test_a_note_is_hidden_from_students_until_the_instructor_shows_it(client, make_user, world):
    _, student = new_student(client, make_user, world)
    document = first_note(client, world)
    assert document["visible_to_students"] is False
    base = f"{API}/courses/{world['course']}/notes"
    assert client.get(base, headers=student).json() == []
    assert client.get(f"{base}/{document['id']}", headers=student).status_code == 404

    assert switch(client, world, document["id"], True).json()["visible_to_students"] is True
    listed = client.get(base, headers=student).json()
    assert [(n["title"], n["concept"]) for n in listed] == [("Loops", "loops")]
    read = client.get(f"{base}/{document['id']}", headers=student)
    assert read.status_code == 200 and "range(5) counts from 0" in read.json()["text"]

    assert switch(client, world, document["id"], False).status_code == 200
    assert client.get(base, headers=student).json() == []
    assert client.get(f"{base}/{document['id']}", headers=student).status_code == 404


def test_hiding_a_note_does_not_stop_the_assistant_using_it(client, owner, world):
    document = first_note(client, world)
    switch(client, world, document["id"], False)
    with owner.connect() as conn:
        chunks = conn.execute(text("SELECT count(*) FROM chunks WHERE document_id = :d"), {"d": document["id"]}).scalar_one()
    assert chunks > 0


def test_outsiders_cannot_read_or_change_notes(client, make_user, world):
    document = first_note(client, world)
    base = f"{API}/courses/{world['course']}/notes"
    switch(client, world, document["id"], True)
    _, outsider = make_user("student")
    assert client.get(base, headers=outsider).status_code == 403
    assert client.get(f"{base}/{document['id']}", headers=outsider).status_code == 403
    _, other_teacher = make_user("instructor")
    patch = client.patch(f"{API}/courses/{world['course']}/documents/{document['id']}", headers=other_teacher,
                         json={"visible_to_students": False})
    assert patch.status_code == 403
    switch(client, world, document["id"], False)


def test_a_note_that_copies_a_solution_needs_a_second_confirmation(client, world):
    url = f"{API}/courses/{world['course']}/documents"
    before = len(client.get(url, headers=world["instructor"]).json())
    refused = client.post(url, headers=world["instructor"], json={"title": "Solved", "text": SOLUTION_NOTE, "visible_to_students": True})
    assert refused.status_code == 409 and "Sum a list" in refused.json()["error"]["message"]
    assert len(client.get(url, headers=world["instructor"]).json()) == before

    hidden = client.post(url, headers=world["instructor"], json={"title": "Solved", "text": SOLUTION_NOTE})
    assert hidden.status_code == 202 and hidden.json()["visible_to_students"] is False
    document = hidden.json()["id"]
    assert switch(client, world, document, True).status_code == 409
    assert switch(client, world, document, True, confirm_solution=True).status_code == 200


def test_an_instructor_sees_every_note_in_the_student_view(client, world):
    document = first_note(client, world)
    switch(client, world, document["id"], False)
    base = f"{API}/courses/{world['course']}/notes"
    titles = [n["title"] for n in client.get(base, headers=world["instructor"]).json()]
    assert "Loops" in titles
