"""Bounded chat history (TR-L-07): a short window per student, reset when the problem changes."""
import json

import redis

TTL_SECONDS = 24 * 3600


def _keys(user_id: int) -> tuple[str, str]:
    return f"chat:{user_id}:history", f"chat:{user_id}:problem"


def window(r: redis.Redis, user_id: int, problem_id: int | None, turns: int) -> list[dict]:
    """The last `turns` exchanges for this problem; a different problem starts a fresh conversation."""
    history_key, problem_key = _keys(user_id)
    current = str(problem_id or 0)
    previous = r.get(problem_key)
    if previous is not None and previous.decode() != current:
        r.delete(history_key)
    r.set(problem_key, current, ex=TTL_SECONDS)
    return [json.loads(item) for item in r.lrange(history_key, -2 * turns, -1)]


def append(r: redis.Redis, user_id: int, turns: int, student: str, assistant: str) -> None:
    history_key, _ = _keys(user_id)
    r.rpush(
        history_key,
        json.dumps({"role": "student", "text": student}),
        json.dumps({"role": "assistant", "text": assistant}),
    )
    r.ltrim(history_key, -2 * turns, -1)
    r.expire(history_key, TTL_SECONDS)
