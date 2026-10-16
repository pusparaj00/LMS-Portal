"""F-05: course announcements from the course's teacher, read by its members."""
import pytest

API = "/api/v1"


def path(course):
    return f"{API}/courses/{course['id']}/announcements"


def post(client, course, title="Exam moved", body="The exam is now on Friday.\nBring a pen."):
    return client.post(path(course), headers=course["instructor"], json={"title": title, "body": body})


def test_post_edit_delete_and_newest_first(client, make_user, course):
    first = post(client, course, title="First")
    assert first.status_code == 201, first.text
    second = post(client, course, title="Second").json()
    assert first.json()["edited_at"] is None and first.json()["body"].endswith("\nBring a pen.")  # line breaks kept

    _, student = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=student)
    titles = [a["title"] for a in client.get(path(course), headers=student).json()]
    assert titles.index("Second") < titles.index("First")

    edited = client.put(f"{path(course)}/{second['id']}", headers=course["instructor"],
                        json={"title": "Second (corrected)", "body": "New text"})
    assert edited.status_code == 200
    assert edited.json()["title"] == "Second (corrected)" and edited.json()["edited_at"] is not None
    assert edited.json()["created_at"] == second["created_at"]

    assert client.delete(f"{path(course)}/{second['id']}", headers=course["instructor"]).status_code == 204
    assert client.delete(f"{path(course)}/{second['id']}", headers=course["instructor"]).status_code == 404
    assert second["id"] not in {a["id"] for a in client.get(path(course), headers=student).json()}


@pytest.mark.parametrize("change", [
    {"title": ""}, {"body": ""}, {"title": "   "}, {"body": " \n "},
    {"title": "x" * 201}, {"body": "x" * 5001}, {"title": "a\x00b"},
])
def test_an_announcement_must_have_a_title_and_text_within_limits(client, course, change):
    body = {"title": "Ok", "body": "Ok", **change}
    assert client.post(path(course), headers=course["instructor"], json=body).status_code == 422


def test_text_is_stored_exactly_as_typed(client, course):
    risky = "<script>alert(1)</script> and <b>bold</b>"
    made = post(client, course, title="<img src=x onerror=alert(1)>", body=risky).json()
    assert made["body"] == risky and made["title"] == "<img src=x onerror=alert(1)>"  # the page shows it as text


def test_only_the_courses_teacher_writes_and_only_members_read(client, make_user, course):
    made = post(client, course).json()
    _, student = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=student)
    _, outsider = make_user("student")
    _, other_teacher = make_user("instructor")
    item = f"{path(course)}/{made['id']}"
    body = {"title": "x", "body": "y"}
    assert client.post(path(course), headers=student, json=body).status_code == 403
    assert client.put(item, headers=student, json=body).status_code == 403
    assert client.delete(item, headers=student).status_code == 403
    assert client.post(path(course), headers=other_teacher, json=body).status_code == 403
    assert client.put(item, headers=other_teacher, json=body).status_code == 403
    assert client.delete(item, headers=other_teacher).status_code == 403
    assert client.get(path(course), headers=outsider).status_code == 403
    assert client.get(path(course)).status_code == 401
    assert client.get(path(course), headers=student).status_code == 200


def test_an_announcement_belongs_to_its_own_course(client, make_user, course):
    made = post(client, course).json()
    _, teacher = make_user("instructor")
    other = client.post(f"{API}/courses", headers=teacher, json={"title": "Other"}).json()
    elsewhere = f"{API}/courses/{other['id']}/announcements/{made['id']}"
    assert client.put(elsewhere, headers=teacher, json={"title": "x", "body": "y"}).status_code == 404
    assert client.delete(elsewhere, headers=teacher).status_code == 404
