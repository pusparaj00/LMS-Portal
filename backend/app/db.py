from functools import lru_cache

import redis
from sqlalchemy import Engine, create_engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url, pool_pre_ping=True, pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow, pool_timeout=settings.db_pool_timeout_s,
    )


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)


@lru_cache
def get_chat_engine() -> Engine:
    """Read-only role used by the chat handlers."""
    settings = get_settings()
    return create_engine(
        settings.chat_database_url, pool_pre_ping=True, pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow, pool_timeout=settings.db_pool_timeout_s,  # a chat request holds both
    )
