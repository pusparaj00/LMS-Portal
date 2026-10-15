"""The mastery service (TR-A-02, F-32). Runs in its own container as the lms_mastery database role.

It is the only process that can write mastery and mastery_events. It accepts evidence, never
mastery values, and only from the API (shared token).
"""
import asyncio
import contextlib
import hmac
import logging
import os
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, text

from app.mastery import service

log = logging.getLogger("app.mastery")
BACKFILL_INTERVAL_SECONDS = 30


async def _backfill_forever() -> None:
    while True:
        try:
            with engine().begin() as conn:
                applied = await asyncio.to_thread(service.backfill, conn)
            if applied:
                log.info("backfilled mastery evidence", extra={"fields": {"submissions": applied}})
        except Exception:
            log.exception("mastery backfill failed")
        await asyncio.sleep(BACKFILL_INTERVAL_SECONDS)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_backfill_forever())
    yield
    task.cancel()


app = FastAPI(title="Mastery service", lifespan=lifespan)


@lru_cache
def engine() -> Engine:
    return create_engine(os.environ["MASTERY_DATABASE_URL"], pool_pre_ping=True)


def authorised(x_service_token: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ["MASTERY_SERVICE_TOKEN"]
    if x_service_token is None or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(401, "invalid service token")


class SubmissionEvidence(BaseModel):
    submission_id: int


class AnswerEvidence(BaseModel):
    user_id: int
    problem_id: int
    correct: bool
    evidence_type: Literal["diagnostic_mcq", "diagnostic_code"]
    evidence_ref: str
    option_id: int | None = None


class ChangeOut(BaseModel):
    concept_id: int
    concept: str
    before: float
    after: float


class ChangesOut(BaseModel):
    changes: list[ChangeOut]


def _out(changes: list[service.Change]) -> ChangesOut:
    return ChangesOut(changes=[ChangeOut(**vars(c)) for c in changes])


@app.get("/health")
def health():
    with engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/evidence/submission", response_model=ChangesOut, dependencies=[Depends(authorised)])
def submission(body: SubmissionEvidence):
    try:
        with engine().begin() as conn:
            return _out(service.record_submission(conn, body.submission_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None


@app.post("/evidence/answer", response_model=ChangesOut, dependencies=[Depends(authorised)])
def answer(body: AnswerEvidence):
    with engine().begin() as conn:
        return _out(service.record_answer(conn, **body.model_dump()))
