"""F-66, F-67, F-68: modules and lesson items, who sees what, safe content types, and completion tracking."""
import base64

import pytest
from sqlalchemy import text

API = "/api/v1"
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture(scope="module")
def world(client, make_user, owner, course):
    """The shared course, two enrolled students, and a second course owned by another teacher."""
    students = []
    for _ in range(2):
        user_id, headers = make_user("student")
        assert client.post(f"{API}/courses/{course['id']}/enroll", headers=headers).status_code == 204
        students.append((user_id, headers))
    other_id, other = make_user("instructor")
    with owner.begin() as conn:
        other_course = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('Elsewhere', :i) RETURNING id"), {"i": other_id}
        ).scalar_one()
    _, outsider = make_user("student")
    return {"students": students, "other": other, "other_course": other_course, "outsider": outsider}


def url(course, path=""):
    return f"{API}/courses/{course['id']}{path}"


def add_module(client, course, title="Week 1", publish=False):
    made = client.post(url(course, "/modules"), headers=course["instructor"], json={"title": title})
    assert made.status_code == 201, made.text
    module = made.json()
    if publish:
        assert client.patch(url(course, f"/modules/{module['id']}"), headers=course["instructor"],
                            json={"published": True}).status_code == 200
    return module


def add_item(client, course, module_id, **fields):
    body = {"kind": "text", "title": "Reading", "body": "Read this."} | fields
    return client.post(url(course, f"/modules/{module_id}/items"), headers=course["instructor"], json=body)


def content(client, course, headers):
    response = client.get(url(course, "/content"), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def titles(data):
    return [m["title"] for m in data["modules"]]


def test_a_draft_module_is_hidden_from_students_until_it_is_published(client, course, world):
    module = add_module(client, course, "Intro draft")
    student = world["students"][0][1]
    assert "Intro draft" not in titles(content(client, course, student))
    assert "Intro draft" in titles(content(client, course, course["instructor"]))
    client.patch(url(course, f"/modules/{module['id']}"), headers=course["instructor"], json={"published": True})
    assert "Intro draft" in titles(content(client, course, student))


def test_a_hidden_item_is_visible_to_staff_only(client, course, world):
    module = add_module(client, course, "With hidden", publish=True)
    add_item(client, course, module["id"], title="Shown")
    add_item(client, course, module["id"], title="Secret", published=False)
    student_view = next(m for m in content(client, course, world["students"][0][1])["modules"] if m["id"] == module["id"])
    staff_view = next(m for m in content(client, course, course["instructor"])["modules"] if m["id"] == module["id"])
    assert [i["title"] for i in student_view["items"]] == ["Shown"] and student_view["total"] == 1
    assert [i["title"] for i in staff_view["items"]] == ["Shown", "Secret"]
    assert [i["published"] for i in staff_view["items"]] == [True, False]


def test_modules_and_items_keep_their_order_and_can_move(client, course):
    first, second, third = (add_module(client, course, f"Order {n}") for n in "ABC")
    ids = [first["id"], second["id"], third["id"]]

    def order():
        return [m["id"] for m in content(client, course, course["instructor"])["modules"] if m["id"] in ids]

    assert order() == ids
    client.post(url(course, f"/modules/{third['id']}/move"), headers=course["instructor"], json={"direction": "up"})
    assert order() == [ids[0], ids[2], ids[1]]
    client.post(url(course, f"/modules/{ids[0]}/move"), headers=course["instructor"], json={"direction": "up"})
    assert order() == [ids[0], ids[2], ids[1]]  # already first: nothing changes

    a, b = (add_item(client, course, first["id"], title=t).json() for t in ("one", "two"))
    client.post(url(course, f"/items/{b['id']}/move"), headers=course["instructor"], json={"direction": "up"})
    module = next(m for m in content(client, course, course["instructor"])["modules"] if m["id"] == first["id"])
    assert [i["id"] for i in module["items"]] == [b["id"], a["id"]]


@pytest.mark.parametrize("link", ["javascript:alert(1)", "ftp://example.com/x", "https://exa mple.com", "//example.com", ""])
def test_a_link_must_be_a_plain_web_address(client, course, link):
    module = add_module(client, course, "Links")
    for kind in ("link", "video"):
        response = add_item(client, course, module["id"], kind=kind, title="x", url=link, body=None)
        assert response.status_code == 422, (kind, link)


def test_link_and_video_items_keep_their_address_and_text_stays_text(client, course):
    module = add_module(client, course, "Types", publish=True)
    link = add_item(client, course, module["id"], kind="link", title="Docs", url=" https://docs.python.org/3/ ", body=None)
    video = add_item(client, course, module["id"], kind="video", title="Talk", url="http://example.com/v", body=None)
    risky = "<script>alert(1)</script> & <b>bold</b>\nsecond line"
    text_item = add_item(client, course, module["id"], title="Note", body=risky)
    assert link.json()["url"] == "https://docs.python.org/3/" and video.json()["kind"] == "video"
    assert text_item.json()["body"] == risky  # stored as typed; the page shows it as text


@pytest.mark.parametrize("fields", [
    {"kind": "text", "body": "x", "url": "https://a.example"},
    {"kind": "link", "body": None, "url": None},
    {"kind": "file", "body": None, "url": None},
    {"kind": "text", "body": "   "},
    {"kind": "text", "title": "   "},
])
def test_an_item_takes_exactly_the_fields_of_its_kind(client, course, fields):
    module = add_module(client, course, "Shapes")
    assert add_item(client, course, module["id"], **fields).status_code == 422


def pdf_item(client, course, module_id, data=PDF, name="Lecture 1.pdf", **extra):
    return add_item(client, course, module_id, kind="file", title="Slides", body=None, pdf_base64=b64(data),
                    file_name=name, **extra)


def test_a_pdf_is_checked_stored_and_downloaded_as_an_attachment(client, course, world):
    module = add_module(client, course, "Files", publish=True)
    made = pdf_item(client, course, module["id"], name="../../evil name?.pdf")
    assert made.status_code == 201, made.text
    item = made.json()
    assert item["file_size"] == len(PDF) and "/" not in item["file_name"] and item["file_name"].endswith(".pdf")
    student = world["students"][0][1]
    got = client.get(url(course, f"/items/{item['id']}/file"), headers=student)
    assert got.status_code == 200 and got.content == PDF
    assert got.headers["content-type"] == "application/pdf" and got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-disposition"].startswith("attachment;") and "/" not in got.headers["content-disposition"]
    assert "pdf_base64" not in str(content(client, course, student))  # the list never carries file bytes


@pytest.mark.parametrize("data", [b"<html><script>alert(1)</script></html>", b"", b"PK\x03\x04 a zip"])
def test_a_file_that_is_not_a_pdf_is_refused(client, course, data):
    module = add_module(client, course, "Not pdf")
    assert pdf_item(client, course, module["id"], data=data or b"x").status_code == 422


def test_a_pdf_over_the_size_limit_or_bad_base64_is_refused(client, course):
    module = add_module(client, course, "Big")
    big = PDF + b"0" * 4_500_001
    assert pdf_item(client, course, module["id"], data=big).status_code == 422
    bad = add_item(client, course, module["id"], kind="file", title="x", body=None, pdf_base64="not base64!!",
                   file_name="a.pdf")
    assert bad.status_code == 422


def test_a_hidden_file_cannot_be_downloaded_by_a_student(client, course, world):
    module = add_module(client, course, "Hidden file", publish=True)
    item = pdf_item(client, course, module["id"], published=False).json()
    assert client.get(url(course, f"/items/{item['id']}/file"), headers=world["students"][0][1]).status_code == 404
    assert client.get(url(course, f"/items/{item['id']}/file"), headers=course["instructor"]).status_code == 200
    assert client.get(url(course, f"/items/{item['id']}/file"), headers=world["outsider"]).status_code == 403


def test_text_cannot_be_changed_into_another_kind_or_given_a_bad_link(client, course):
    module = add_module(client, course, "Edit")
    note = add_item(client, course, module["id"]).json()
    link = add_item(client, course, module["id"], kind="link", title="L", url="https://a.example", body=None).json()
    edit = lambda item, **body: client.patch(url(course, f"/items/{item['id']}"), headers=course["instructor"], json=body)  # noqa: E731
    assert edit(note, body="New text", title="Renamed").json()["body"] == "New text"
    assert edit(note, url="https://a.example").status_code == 422  # a text item has no address
    assert edit(link, body="text").status_code == 422
    assert edit(link, url="javascript:alert(1)").status_code == 422
    assert edit(link, url="https://b.example").json()["url"] == "https://b.example"
    assert edit(note).status_code == 422


def test_only_the_courses_own_teacher_edits_and_items_stay_inside_their_course(client, course, world):
    module = add_module(client, course, "Mine", publish=True)
    item = add_item(client, course, module["id"]).json()
    other = world["other"]
    assert client.post(url(course, "/modules"), headers=other, json={"title": "x"}).status_code == 403
    assert client.delete(url(course, f"/items/{item['id']}"), headers=other).status_code == 403
    assert client.get(url(course, "/content"), headers=world["outsider"]).status_code == 403
    # the item exists, but not in the other teacher's own course
    elsewhere = f"{API}/courses/{world['other_course']}"
    assert client.patch(f"{elsewhere}/items/{item['id']}", headers=other, json={"title": "stolen"}).status_code == 404
    assert client.delete(f"{elsewhere}/modules/{module['id']}", headers=other).status_code == 404


def test_a_student_marks_items_done_and_sees_progress(client, course, world):
    module = add_module(client, course, "Progress", publish=True)
    one, two = (add_item(client, course, module["id"], title=t).json() for t in ("p1", "p2"))
    hidden = add_item(client, course, module["id"], title="p3", published=False).json()
    student = world["students"][0][1]
    mark = lambda item: client.put(url(course, f"/items/{item['id']}/completion"), headers=student)  # noqa: E731
    assert mark(one).status_code == 204 and mark(one).status_code == 204  # saying it twice changes nothing
    data = content(client, course, student)
    mine = next(m for m in data["modules"] if m["id"] == module["id"])
    assert (mine["completed"], mine["total"]) == (1, 2)
    assert [i["completed"] for i in mine["items"]] == [True, False]
    assert data["completed"] >= 1 and data["total"] >= 2
    assert mark(hidden).status_code == 404  # a hidden item is not there for a student
    assert client.delete(url(course, f"/items/{one['id']}/completion"), headers=student).status_code == 204
    assert next(m for m in content(client, course, student)["modules"] if m["id"] == module["id"])["completed"] == 0
    assert client.put(url(course, f"/items/{two['id']}/completion"), headers=course["instructor"]).status_code == 403
    assert client.put(url(course, f"/items/{two['id']}/completion"), headers=world["outsider"]).status_code == 403


def test_one_students_progress_is_not_another_students(client, course, world):
    module = add_module(client, course, "Private progress", publish=True)
    item = add_item(client, course, module["id"]).json()
    first, second = world["students"][0][1], world["students"][1][1]
    client.put(url(course, f"/items/{item['id']}/completion"), headers=first)
    seen = next(m for m in content(client, course, second)["modules"] if m["id"] == module["id"])
    assert seen["completed"] == 0 and seen["items"][0]["completed"] is False


def test_the_teacher_sees_a_completion_rate_per_module(client, course, world):
    module = add_module(client, course, "Rate", publish=True)
    items = [add_item(client, course, module["id"], title=t).json() for t in ("r1", "r2")]
    (_, first), (_, second) = world["students"]
    for item in items:
        client.put(url(course, f"/items/{item['id']}/completion"), headers=first)
    client.put(url(course, f"/items/{items[0]['id']}/completion"), headers=second)
    staff = next(m for m in content(client, course, course["instructor"])["modules"] if m["id"] == module["id"])
    assert staff["completion_rate"] == 75.0  # 3 of 2 items x 2 students
    assert staff["completed"] is None and staff["items"][0]["completed"] is None  # no personal flags for staff
    empty = add_module(client, course, "No items", publish=True)
    assert next(m for m in content(client, course, course["instructor"])["modules"]
                if m["id"] == empty["id"])["completion_rate"] is None


def test_the_student_dashboard_counts_content_progress(client, course, world):
    stats = client.get(f"{API}/students/me/stats", headers=world["students"][0][1]).json()
    mine = next(c for c in stats["courses"] if c["course_id"] == course["id"])
    assert mine["content_total"] > 0 and 0 <= mine["content_done"] <= mine["content_total"]


def test_deleting_a_module_removes_its_items_and_completions(client, owner, course, world):
    module = add_module(client, course, "Doomed", publish=True)
    item = add_item(client, course, module["id"]).json()
    client.put(url(course, f"/items/{item['id']}/completion"), headers=world["students"][0][1])
    assert client.delete(url(course, f"/modules/{module['id']}"), headers=course["instructor"]).status_code == 204
    with owner.connect() as conn:
        left = conn.execute(
            text("SELECT (SELECT count(*) FROM content_items WHERE id = :i) + (SELECT count(*) FROM item_completions"
                 " WHERE item_id = :i) + (SELECT count(*) FROM modules WHERE id = :m)"),
            {"i": item["id"], "m": module["id"]},
        ).scalar_one()
    assert left == 0
    assert client.delete(url(course, f"/modules/{module['id']}"), headers=course["instructor"]).status_code == 404


def test_a_lesson_file_upload_has_its_own_size_limit_and_nothing_else_gains_it(client, course):
    module = add_module(client, course, "Limits")
    too_big = {"kind": "file", "title": "x", "pdf_base64": "A" * 6_300_000, "file_name": "a.pdf"}
    assert client.post(url(course, f"/modules/{module['id']}/items"), headers=course["instructor"],
                       json=too_big).status_code == 413
    assert client.post(url(course, "/modules"), headers=course["instructor"],
                       json={"title": "x" * 1_000_000}).status_code == 413
