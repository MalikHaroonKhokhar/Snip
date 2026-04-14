import pytest

from app.services import cache_service


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_set_get_delete_roundtrip_against_upstash():
    key = "pytest_roundtrip_xyz"
    try:
        await cache_service.set_in_cache(key, "https://example.com/rt", ttl=30)
        assert await cache_service.get_from_cache(key) == "https://example.com/rt"
        await cache_service.delete_from_cache(key)
        assert await cache_service.get_from_cache(key) is None
    finally:
        await cache_service.delete_from_cache(key)


async def test_ttl_is_honoured_on_setex():
    client = await cache_service.get_redis()
    key = "pytest_ttl_xyz"
    try:
        await cache_service.set_in_cache(key, "https://x", ttl=45)
        ttl = await client.ttl(f"{cache_service.KEY_PREFIX}{key}")
        assert 0 < ttl <= 45
    finally:
        await cache_service.delete_from_cache(key)
