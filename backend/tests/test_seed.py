"""TR-D-06: the seed's building blocks are safe to run twice. (The whole seed is run twice in the clean-clone check.)"""
import pytest
from sqlalchemy import text

from app.auth import verify_password
from app.notes_import import stage_notes
from app.seed import ensure_user
from tests.test_feedback_api import world  # noqa: F401  (fixture)

NOTE = "---\ntitle: Seed note\nconcept: loops\nstatus: needs human review\n---\n## Part\nSome words about loops.\n"


@pytest.fixture
def clean_users(owner):
    emails = ["seed-a@seed.test", "seed-b@seed.test", "seed-c@seed.test"]
    delete = text("DELETE FROM users WHERE email LIKE '%@seed.test'")
    with owner.begin() as conn:
        conn.execute(delete)
    yield emails
    with owner.begin() as conn:
        conn.execute(delete)


def test_a_created_account_gets_the_given_password_and_a_second_run_changes_nothing(owner, clean_users):
    email = clean_users[0]
    with owner.begin() as conn:
        user_id, generated = ensure_user(conn, email, "student", "chosen-password-1")
        assert generated is None
        again_id, again_generated = ensure_user(conn, email, "student", "a-different-password")
        assert (again_id, again_generated) == (user_id, None)
        stored = conn.execute(text("SELECT password_hash FROM users WHERE id = :i"), {"i": user_id}).scalar_one()
    assert verify_password("chosen-password-1", stored) and not verify_password("a-different-password", stored)


def test_without_a_password_a_random_one_is_generated_and_returned_once(owner, clean_users):
    with owner.begin() as conn:
        first_id, password = ensure_user(conn, clean_users[1], "instructor", None)
        second_id, second_password = ensure_user(conn, clean_users[1], "instructor", None)
        other_id, other_password = ensure_user(conn, clean_users[2], "instructor", "")
        stored = conn.execute(text("SELECT password_hash, role FROM users WHERE id = :i"), {"i": first_id}).one()
    assert password and len(password) >= 12 and verify_password(password, stored.password_hash) and stored.role == "instructor"
    assert (second_id, second_password) == (first_id, None)
    assert other_password and other_password != password  # no shared default password


@pytest.mark.parametrize("password", ["short", "x" * 73])
def test_unusable_passwords_are_refused_not_stored(owner, clean_users, password):
    with pytest.raises(SystemExit):
        with owner.begin() as conn:
            ensure_user(conn, clean_users[0], "student", password)
    with owner.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users WHERE email = :e"), {"e": clean_users[0]}).scalar_one() == 0


def test_unchanged_embedded_notes_are_skipped_and_changed_ones_are_queued_again(world, owner, tmp_path):
    (tmp_path / "seed-note.md").write_text(NOTE, encoding="utf-8")
    with owner.begin() as conn:
        queued, skipped = stage_notes(conn, world["course"], tmp_path)
    assert len(queued) == 1 and skipped == 0
    with owner.begin() as conn:
        conn.execute(text("UPDATE documents SET status = 'ready' WHERE id = :d"), {"d": queued[0]})
    with owner.begin() as conn:
        assert stage_notes(conn, world["course"], tmp_path) == ([], 1)  # nothing to do the second time
    (tmp_path / "seed-note.md").write_text(NOTE.replace("Some words", "Other words"), encoding="utf-8")
    with owner.begin() as conn:
        again, skipped = stage_notes(conn, world["course"], tmp_path)
    assert again == queued and skipped == 0  # the same document, queued for re-embedding


def test_a_note_with_an_unknown_concept_stops_the_seed(world, owner, tmp_path):
    (tmp_path / "bad.md").write_text(NOTE.replace("concept: loops", "concept: nonsense"), encoding="utf-8")
    with pytest.raises(SystemExit, match="unknown concept"):
        with owner.begin() as conn:
            stage_notes(conn, world["course"], tmp_path)
