import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None

KEY_PREFIX = "url:"


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.upstash_redis_url, decode_responses=True
        )
    return _redis_client


async def ping() -> bool:
    return await (await get_redis()).ping()


async def get_from_cache(short_code: str) -> str | None:
    """Read-through lookup. Returns None on miss OR on any cache failure."""
    try:
        client = await get_redis()
        return await client.get(f"{KEY_PREFIX}{short_code}")
    except Exception as e:
        logger.warning("cache GET failed for %s: %s", short_code, e)
        return None


async def set_in_cache(short_code: str, long_url: str, ttl: int | None = None) -> None:
    """Write-through population. Swallows failures — DB is source of truth."""
    try:
        client = await get_redis()
        await client.setex(
            f"{KEY_PREFIX}{short_code}", ttl or settings.cache_ttl_seconds, long_url
        )
    except Exception as e:
        logger.warning("cache SET failed for %s: %s", short_code, e)


async def delete_from_cache(short_code: str) -> None:
    """Manual invalidation (e.g. from cleanup service). Non-fatal on failure."""
    try:
        client = await get_redis()
        await client.delete(f"{KEY_PREFIX}{short_code}")
    except Exception as e:
        logger.warning("cache DELETE failed for %s: %s", short_code, e)
