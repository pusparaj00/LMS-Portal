"""TR-M-08: each chat question is stored with its route and the concept it is about, decided by rule, not by the model."""
from sqlalchemy import text

from app.chat.handlers import _forms
from tests.test_chat_api import say
from tests.test_feedback_api import FakeLLM, llm, new_student, world  # noqa: F401  (fixtures)

API = "/api/v1"


def question_tags(owner, user_id):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT route, concept_id FROM chat_messages WHERE user_id = :u AND role = 'user' ORDER BY id"),
            {"u": user_id},
        ).all()


def test_a_concept_is_recognised_by_its_name_parts_and_singular():
    assert {"tuples sets", "tuples", "sets", "tuple", "set"} <= _forms("tuples_sets")
    assert {"class", "dictionary", "loop"} <= _forms("classes") | _forms("dictionaries") | _forms("loops")
    assert "io" not in _forms("variables_io")  # too short to tell apart from other words


def test_a_question_is_tagged_with_the_concept_it_names_else_the_open_problems(client, make_user, world, owner, llm):
    user_id, headers = new_student(client, make_user, world)
    llm(FakeLLM())
    say(client, headers, "why does my loop never stop", route="recommend")
    say(client, headers, "hello there", route="recommend")
    say(client, headers, "I am stuck here", route="recommend", problem_id=world["p"])
    loops = world["loops"]
    assert question_tags(owner, user_id) == [("recommend", loops), ("recommend", None), ("recommend", loops)]


def test_the_longest_name_wins_and_a_word_inside_another_does_not_count(client, make_user, owner, llm):
    _, teacher = make_user("instructor")
    course = client.post(f"{API}/courses", headers=teacher, json={"title": "Tagging"}).json()["id"]
    ids = {name: client.post(f"{API}/courses/{course}/concepts", headers=teacher, json={"name": name}).json()["concept_id"]
           for name in ("lists", "comprehensions", "tuples_sets")}
    user_id, headers = make_user("student")
    assert client.post(f"{API}/courses/{course}/enroll", headers=headers).status_code == 204
    llm(FakeLLM())
    for message in ("my list comprehension is wrong", "how do I reset everything", "what is a set"):
        say(client, headers, message, route="recommend")
    assert [k for _, k in question_tags(owner, user_id)] == [ids["comprehensions"], None, ids["tuples_sets"]]


def test_a_concept_asked_about_in_chat_cannot_be_deleted(client, make_user, owner, llm):
    _, teacher = make_user("instructor")
    course = client.post(f"{API}/courses", headers=teacher, json={"title": "Asked about"}).json()["id"]
    concept = client.post(f"{API}/courses/{course}/concepts", headers=teacher, json={"name": "recursion"}).json()
    _, headers = make_user("student")
    client.post(f"{API}/courses/{course}/enroll", headers=headers)
    llm(FakeLLM())
    say(client, headers, "what is recursion", route="recommend")
    refused = client.delete(f"{API}/courses/{course}/concepts/{concept['concept_id']}", headers=teacher)
    assert refused.status_code == 409 and "chat questions" in refused.json()["error"]["message"]
