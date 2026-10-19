"""TR-S-05: a student must agree to the privacy notice before their data is processed, and can withdraw."""
import pytest
from sqlalchemy import text

from app import consent
from app.config import Settings
from tests.helpers import enroll
from tests.test_feedback_api import FakeLLM, explain, failed_submission, good_reply, llm, new_student, world  # noqa: F401

API = "/api/v1"
BASE = dict(database_url="x", redis_url="x", jwt_secret="x", mastery_service_url="x", mastery_service_token="x")


def settings(**changes) -> Settings:
    return Settings(**{**BASE, **changes})


def status(client, headers):
    return client.get(f"{API}/consent", headers=headers).json()


def agree(client, headers):
    version = client.get(f"{API}/consent/notice", headers=headers).json()["version"]
    return client.post(f"{API}/consent/accept", headers=headers, json={"version": version, "adult": True})


@pytest.fixture
def newcomer(make_user):
    return make_user("student", consented=False)


def test_a_new_student_has_not_agreed_and_the_notice_says_what_is_collected_and_who_receives_it(client, newcomer):
    _, headers = newcomer
    assert status(client, headers)["accepted"] is False
    notice = client.get(f"{API}/consent/notice", headers=headers).json()
    headings = [s["heading"] for s in notice["sections"]]
    assert headings[:4] == ["Who can use this", "What is collected", "Why", "Who receives it"] and "Withdrawing" in headings
    everything = " ".join(p for s in notice["sections"] for p in s["paragraphs"])
    for word in ("code", "answers", "messages", "mastery", "instructor", "draft"):
        assert word in everything
    assert notice["version"] == consent.CONSENT_VERSION


def test_nothing_is_processed_for_a_student_who_has_not_agreed(client, world, newcomer):
    _, headers = newcomer
    assert enroll(client, world['course'], headers).status_code == 200  # enrolling is fine
    blocked = [
        client.post(f"{API}/submissions", headers=headers, json={"problem_id": world["p"], "code": "print(1)"}),
        client.post(f"{API}/submissions/run", headers=headers, json={"problem_id": world["p"], "code": "print(1)"}),
        client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": world["course"]}),
        client.post(f"{API}/chat", headers=headers, json={"message": "hello"}),
        client.post(f"{API}/submissions/1/explain", headers=headers),
        client.post(f"{API}/submissions/1/hint", headers=headers),
        client.post(f"{API}/probes/{world['m']}/answer", headers=headers, json={"submission_id": 1, "option_id": 1}),
    ]
    assert [r.status_code for r in blocked] == [403] * 7
    assert all("agreed to the privacy notice" in r.json()["error"]["message"] for r in blocked)


def test_the_student_can_still_read_their_own_mastery_and_the_notice_without_agreeing(client, world, newcomer):
    _, headers = newcomer
    enroll(client, world['course'], headers)
    mastery = client.get(f"{API}/students/me/mastery", params={"course_id": world["course"]}, headers=headers)
    assert mastery.status_code == 200
    assert client.get(f"{API}/consent/notice", headers=headers).status_code == 200


def test_agreeing_records_a_timestamp_unlocks_processing_and_is_idempotent(client, world, owner, newcomer):
    user_id, headers = newcomer
    enroll(client, world['course'], headers)
    first = agree(client, headers)
    assert first.status_code == 200 and first.json()["accepted"] is True and first.json()["accepted_at"]
    again = agree(client, headers)
    assert again.json()["accepted_at"] == first.json()["accepted_at"]
    with owner.connect() as conn:
        rows = conn.execute(text("SELECT version, withdrawn_at FROM consents WHERE user_id = :u"), {"u": user_id}).all()
    assert [tuple(r) for r in rows] == [(consent.CONSENT_VERSION, None)]  # one record, not two
    ok = client.post(f"{API}/submissions", headers=headers, json={"problem_id": world["p"], "code": "print(1)"})
    assert ok.status_code == 200


def test_withdrawing_stops_processing_at_once_and_keeps_the_record(client, world, owner, newcomer):
    user_id, headers = newcomer
    enroll(client, world['course'], headers)
    agree(client, headers)
    withdrawn = client.post(f"{API}/consent/withdraw", headers=headers).json()
    assert withdrawn["accepted"] is False and withdrawn["withdrawn_at"] and withdrawn["accepted_at"] is None
    assert client.post(f"{API}/submissions", headers=headers, json={"problem_id": world["p"], "code": "x"}).status_code == 403
    assert client.post(f"{API}/chat", headers=headers, json={"message": "hi"}).status_code == 403
    with owner.connect() as conn:
        row = conn.execute(text("SELECT accepted_at, withdrawn_at FROM consents WHERE user_id = :u"), {"u": user_id}).one()
    assert row.accepted_at is not None and row.withdrawn_at >= row.accepted_at
    assert agree(client, headers).json()["accepted"] is True  # they may agree again, which makes a new record
    with owner.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM consents WHERE user_id = :u"), {"u": user_id}).scalar_one() == 2


def test_a_changed_notice_asks_everyone_again_and_a_stale_acceptance_is_refused(client, newcomer, monkeypatch):
    _, headers = newcomer
    agree(client, headers)
    assert status(client, headers)["accepted"] is True
    monkeypatch.setattr(consent, "CONSENT_VERSION", "2099-01-v2")
    assert status(client, headers)["accepted"] is False
    stale = client.post(f"{API}/consent/accept", headers=headers, json={"version": "2026-10-v1"})
    assert stale.status_code == 409 and "changed" in stale.json()["error"]["message"]


def test_withdrawing_when_nothing_was_agreed_changes_nothing(client, newcomer):
    _, headers = newcomer
    result = client.post(f"{API}/consent/withdraw", headers=headers)
    assert result.status_code == 200 and result.json()["accepted"] is False and result.json()["withdrawn_at"] is None


def test_only_students_have_a_consent_state(client, make_user):
    _, instructor = make_user("instructor")
    assert client.get(f"{API}/consent", headers=instructor).status_code == 403
    assert client.get(f"{API}/consent/notice", headers=instructor).status_code == 200
    assert client.get(f"{API}/consent/notice").status_code == 401


def test_the_notice_names_only_the_providers_that_are_really_configured_in_the_order_they_are_tried():
    def names(s):
        return [p.name for p in consent.configured_providers(s)]

    chain = settings(
        llm_provider="gemini_pro", gemini_pro_api_key="k", gemini_api_key="k2", groqcloud_api_key="g",
        llm_fallback="gemini_pro:gemini-3.1-pro-preview,gemini,groq,mistral,openai,local",  # no mistral/openai/local keys
    )
    assert names(chain) == ["Google (Gemini)", "Groq"]  # Google once, and unconfigured providers left out
    assert consent.configured_providers(chain)[0].order == "first choice"
    assert consent.configured_providers(chain)[1].order == "only if the one before fails"
    assert names(settings()) == []  # the stub sends nothing anywhere
    local = settings(llm_provider="local", local_llm_base_url="http://llm.internal/v1")
    assert names(local) == ["A model run by your institution; requests stay inside it"]


def test_with_no_provider_the_notice_says_nothing_is_sent_outside(client, newcomer, monkeypatch):
    _, headers = newcomer
    monkeypatch.setattr(consent, "get_settings", lambda: settings())
    notice = client.get(f"{API}/consent/notice", headers=headers).json()
    who = " ".join(notice["sections"][3]["paragraphs"])
    assert notice["providers"] == [] and "No model provider is configured" in who


def test_the_prompts_sent_to_the_model_hold_no_email_address_or_name(client, world, owner, llm, make_user):  # noqa: F811
    """TR-S-06: the notice promises that no name or email is added to what the provider receives."""
    user_id, headers = new_student(client, make_user, world)
    with owner.connect() as conn:
        email = conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": user_id}).scalar_one()
    name = "Zephyrine Okonkwo-Lindqvist"  # a display name the teacher sees (F-01); it must never reach the model
    assert client.patch(f"{API}/me", headers=headers, json={"display_name": name}).status_code == 200
    sid = failed_submission(client, world, headers)
    fake = llm(FakeLLM(good_reply(owner, sid, world)))
    assert explain(client, headers, sid).json()["status"] == "verified"
    chat_fake = llm(FakeLLM('{"route": "general", "confidence": 0.9}', "A reply."))
    client.post(f"{API}/chat", headers=headers, json={"message": "What is a loop?", "problem_id": world["p"]})
    prompts = " ".join(system + user for system, user in [*fake.calls, *chat_fake.calls])
    assert fake.calls and chat_fake.calls
    assert email not in prompts and email.split("@")[0] not in prompts
    assert "Zephyrine" not in prompts and "Lindqvist" not in prompts


def test_agreeing_needs_the_student_to_confirm_they_are_an_adult(client, newcomer, owner):
    """TR-S-10: without the confirmation nothing is recorded and the student stays blocked."""
    user_id, headers = newcomer
    version = client.get(f"{API}/consent/notice", headers=headers).json()["version"]
    notice = client.get(f"{API}/consent/notice", headers=headers).json()
    assert notice["sections"][0]["heading"] == "Who can use this" and "18" in notice["sections"][0]["paragraphs"][0]
    for body in ({"version": version}, {"version": version, "adult": False}):
        refused = client.post(f"{API}/consent/accept", headers=headers, json=body)
        assert refused.status_code == 422 and "18" in refused.json()["error"]["message"]
    assert status(client, headers)["accepted"] is False
    assert client.post(f"{API}/chat", headers=headers, json={"message": "hello"}).status_code == 403
    assert agree(client, headers).json()["accepted"] is True
    with owner.connect() as conn:
        assert conn.execute(
            text("SELECT adult_confirmed FROM consents WHERE user_id = :u"), {"u": user_id}
        ).scalar_one() is True
