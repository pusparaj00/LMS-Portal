from functools import lru_cache

import redis
from sqlalchemy import Engine, create_engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)


@lru_cache
def get_chat_engine() -> Engine:
    """Read-only role used by the chat handlers."""
    return create_engine(get_settings().chat_database_url, pool_pre_ping=True)
