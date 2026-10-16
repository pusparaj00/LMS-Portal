"""Background worker: embeds course notes so no request waits for it (TR-A-07).

Jobs are document ids in a Redis list. A job moves to a processing list while it runs and is put
back if the worker dies, so a crash loses nothing; re-running a job replaces the chunks, so it never
duplicates them.
"""
import logging
import os
import time

import redis
from sqlalchemy import create_engine, text

from app import erasure
from app.logging import configure_logging
from app.mastery.client import erase_user
from app.retrieval import store

PROCESSING = "ingest:processing"
FAILED = "ingest:failed"
ATTEMPTS = "ingest:attempts"
HEARTBEAT = "worker:heartbeat"
MAX_ATTEMPTS = 3
POLL_SECONDS = 5
ERASURE_SWEEP_SECONDS = 60

log = logging.getLogger("app.worker")


def _fail(conn, document_id: int, detail: str) -> None:
    conn.execute(
        text("UPDATE documents SET status = 'failed', status_detail = :d WHERE id = :i"),
        {"d": detail[:300], "i": document_id},
    )


def process(r: redis.Redis, engine, job: bytes) -> None:
    document_id = int(job)
    try:
        with engine.begin() as conn:
            chunks = store.ingest_document(conn, document_id)
        log.info("ingested", extra={"fields": {"document_id": document_id, "chunks": chunks}})
        r.hdel(ATTEMPTS, job)
        r.lrem(PROCESSING, 1, job)
    except Exception as exc:
        attempts = r.hincrby(ATTEMPTS, job, 1)
        log.exception("ingestion failed", extra={"fields": {"document_id": document_id, "attempt": attempts}})
        r.lrem(PROCESSING, 1, job)
        if attempts < MAX_ATTEMPTS:
            r.rpush(store.QUEUE, job)
        else:
            r.rpush(FAILED, job)
            with engine.begin() as conn:
                _fail(conn, document_id, f"{type(exc).__name__}: {exc}")


def sweep_erasures(engine) -> None:
    """Schedules retention erasures (TR-S-07) and carries out requests whose 48-hour notice is over."""
    days = int(os.environ.get("RETENTION_DAYS", "0"))
    if days:
        with engine.begin() as conn:
            erasure.schedule_retention(conn, days)
    url, token = os.environ["MASTERY_SERVICE_URL"], os.environ["MASTERY_SERVICE_TOKEN"]
    erasure.run_due(engine, lambda user_id: erase_user(user_id, url=url, token=token))


def requeue_interrupted(r: redis.Redis) -> int:
    """Jobs left in the processing list belong to a worker that died; run them again."""
    count = 0
    while r.lmove(PROCESSING, store.QUEUE, "LEFT", "RIGHT") is not None:
        count += 1
    return count


def main() -> None:
    configure_logging()
    # The socket timeout must outlast the blocking wait below, or an idle worker times out and crashes.
    r = redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=POLL_SECONDS + 10)
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    log.info("worker started", extra={"fields": {"requeued": requeue_interrupted(r)}})
    last_sweep = 0.0
    while True:
        try:
            r.set(HEARTBEAT, str(time.time()), ex=30)
            if time.monotonic() - last_sweep >= ERASURE_SWEEP_SECONDS:
                last_sweep = time.monotonic()
                try:
                    sweep_erasures(engine)
                except Exception:
                    log.exception("erasure sweep failed")
            job = r.blmove(store.QUEUE, PROCESSING, POLL_SECONDS, "LEFT", "RIGHT")
            if job is not None:
                process(r, engine, job)
        except redis.RedisError:
            log.exception("redis unavailable, retrying")
            time.sleep(2)


if __name__ == "__main__":
    main()
