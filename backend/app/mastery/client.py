"""How the API reports evidence to the mastery service. The API never writes mastery itself."""
import httpx

from app.config import get_settings
from app.schemas import MasteryChange


class MasteryUnavailable(Exception):
    pass


def _post(path: str, payload: dict) -> list[MasteryChange]:
    settings = get_settings()
    try:
        response = httpx.post(
            f"{settings.mastery_service_url}{path}",
            json=payload,
            headers={"X-Service-Token": settings.mastery_service_token},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MasteryUnavailable(str(exc)) from exc
    return [
        MasteryChange(concept=c["concept"], before=c["before"], after=c["after"])
        for c in response.json()["changes"]
    ]


def erase_user(user_id: int, *, url: str, token: str) -> None:
    """Asks the mastery service to delete this user's mastery rows (TR-S-07); safe to repeat."""
    try:
        httpx.post(
            f"{url}/erase", json={"user_id": user_id}, headers={"X-Service-Token": token}, timeout=10
        ).raise_for_status()
    except httpx.HTTPError as exc:
        raise MasteryUnavailable(str(exc)) from exc


def record_submission(submission_id: int) -> list[MasteryChange]:
    return _post("/evidence/submission", {"submission_id": submission_id})


def record_answer(
    *, user_id: int, problem_id: int, correct: bool, evidence_type: str, evidence_ref: str,
    option_id: int | None, dont_know: bool = False, confidence: str | None = None,
) -> list[MasteryChange]:
    return _post(
        "/evidence/answer",
        {
            "user_id": user_id, "problem_id": problem_id, "correct": correct,
            "evidence_type": evidence_type, "evidence_ref": evidence_ref, "option_id": option_id,
            "dont_know": dont_know, "confidence": confidence,
        },
    )


def record_pooled(*, user_id: int, course_id: int, prior_mean: float, evidence_ref: str) -> list[MasteryChange]:
    return _post(
        "/evidence/pooled",
        {"user_id": user_id, "course_id": course_id, "prior_mean": prior_mean, "evidence_ref": evidence_ref},
    )
