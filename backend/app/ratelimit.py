"""Rate limits (TR-S-04): fixed windows counted in Redis, so every API process shares them.

A limit that is exceeded answers 429 with a Retry-After header. If Redis is unreachable the request is
allowed: losing the limiter must not take the whole service down, and the failure is logged.
"""
import logging
import time
from dataclasses import dataclass

import redis
from fastapi import HTTPException, Request

from app.db import get_redis

log = logging.getLogger("app.ratelimit")


@dataclass(frozen=True)
class Rule:
    limit: int
    window_seconds: int


# Generous for a student working normally, tight for a script. Keyed per user, per email or per address.
RULES: dict[str, Rule] = {
    "login_email": Rule(10, 60),
    "login_ip": Rule(60, 60),
    "register_ip": Rule(100, 3600),  # a whole lab class often shares one campus address
    "run": Rule(60, 60),
    "run_custom": Rule(60, 60),
    "submit": Rule(30, 60),
    "chat": Rule(30, 60),
    "explain": Rule(15, 60),
    "hint": Rule(30, 60),
    "diagnostic_answer": Rule(60, 60),
    "probe": Rule(30, 60),
    "draft": Rule(10, 3600),  # each draft is up to two model calls and two sandbox runs per attempt
    "work_upload": Rule(20, 60),  # each save may carry a file of several MB
    "work_comment": Rule(30, 60),
    "lti": Rule(120, 60),  # per address; a class opening the tool together shares one campus address
}


def client_ip(request: Request) -> str:
    """The nginx front end sets X-Forwarded-For to the real address; direct callers fall back to the socket."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def check(name: str, subject: str | int) -> None:
    rule = RULES[name]
    now = time.time()
    bucket = int(now // rule.window_seconds)
    key = f"rl:{name}:{subject}:{bucket}"
    try:
        r = get_redis()
        count = int(r.incr(key))
        if count == 1:
            r.expire(key, rule.window_seconds + 1)
    except redis.RedisError:
        log.exception("rate limiter unavailable, allowing the request", extra={"fields": {"rule": name}})
        return
    if count > rule.limit:
        retry = max(1, int((bucket + 1) * rule.window_seconds - now) + 1)
        raise HTTPException(
            429,
            f"Too many requests. Try again in {retry} seconds.",
            headers={"Retry-After": str(retry)},
        )
