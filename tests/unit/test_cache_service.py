from unittest.mock import AsyncMock

import pytest

from app.services import cache_service


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_get_uses_url_prefix(monkeypatch):
    client = AsyncMock()
    client.get.return_value = "https://example.com"
    monkeypatch.setattr(cache_service, "get_redis", AsyncMock(return_value=client))

    result = await cache_service.get_from_cache("abc1234")

    assert result == "https://example.com"
    client.get.assert_awaited_once_with("url:abc1234")


async def test_setex_uses_url_prefix_and_ttl(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(cache_service, "get_redis", AsyncMock(return_value=client))

    await cache_service.set_in_cache("abc1234", "https://example.com", ttl=120)

    client.setex.assert_awaited_once_with("url:abc1234", 120, "https://example.com")


async def test_set_defaults_to_configured_ttl(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(cache_service, "get_redis", AsyncMock(return_value=client))

    await cache_service.set_in_cache("abc", "https://x")

    args, _ = client.setex.call_args
    # positional: (key, ttl, value)
    assert args[1] == cache_service.settings.cache_ttl_seconds


async def test_delete_uses_url_prefix(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(cache_service, "get_redis", AsyncMock(return_value=client))

    await cache_service.delete_from_cache("abc1234")

    client.delete.assert_awaited_once_with("url:abc1234")


async def test_get_returns_none_on_exception(monkeypatch):
    async def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(cache_service, "get_redis", boom)

    assert await cache_service.get_from_cache("x") is None


async def test_set_swallows_exception(monkeypatch):
    async def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(cache_service, "get_redis", boom)

    # Must not raise — DB is source of truth
    await cache_service.set_in_cache("x", "https://x", ttl=60)


async def test_delete_swallows_exception(monkeypatch):
    async def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(cache_service, "get_redis", boom)

    await cache_service.delete_from_cache("x")
