from collections.abc import AsyncGenerator

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import get_settings

_redis_client: Redis | None = None


async def init_redis() -> Redis:
    """Create the shared Redis client."""
    global _redis_client
    settings = get_settings()
    _redis_client = redis.from_url(
        str(settings.redis_url),
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis_client.ping()
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def get_redis_client() -> Redis:
    if _redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return _redis_client


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency that yields the shared Redis client."""
    yield get_redis_client()
