from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.models.url_model import ShortenRequest
from app.services import url_service


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _fake_db():
    db = MagicMock()
    db.urls.insert_one = AsyncMock()
    db.urls.find_one = AsyncMock()
    db.urls.update_one = AsyncMock()
    return db


async def test_create_short_url_writes_db_then_cache(monkeypatch):
    db = _fake_db()
    set_cache = AsyncMock()
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(url_service, "set_in_cache", set_cache)
    monkeypatch.setattr(url_service, "generate_short_code", lambda: "abc1234")

    result = await url_service.create_short_url(
        ShortenRequest(long_url="https://example.com/x")
    )

    assert result.short_code == "abc1234"
    assert result.short_url.endswith("/abc1234")
    db.urls.insert_one.assert_awaited_once()
    set_cache.assert_awaited_once()
    # cache is written with (code, long_url)
    args, _ = set_cache.call_args
    assert args[0] == "abc1234"
    assert args[1] == "https://example.com/x"


async def test_create_short_url_retries_on_collision(monkeypatch):
    db = _fake_db()
    db.urls.insert_one.side_effect = [DuplicateKeyError("dup"), DuplicateKeyError("dup"), None]
    codes = iter(["c1", "c2", "c3"])
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(url_service, "set_in_cache", AsyncMock())
    monkeypatch.setattr(url_service, "generate_short_code", lambda: next(codes))

    result = await url_service.create_short_url(
        ShortenRequest(long_url="https://example.com")
    )

    assert result.short_code == "c3"
    assert db.urls.insert_one.await_count == 3


async def test_create_short_url_gives_up_after_three_collisions(monkeypatch):
    db = _fake_db()
    db.urls.insert_one.side_effect = DuplicateKeyError("dup")
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(url_service, "set_in_cache", AsyncMock())
    monkeypatch.setattr(url_service, "generate_short_code", lambda: "xxx")

    with pytest.raises(url_service.ShortCodeGenerationError):
        await url_service.create_short_url(
            ShortenRequest(long_url="https://example.com")
        )
    assert db.urls.insert_one.await_count == 3


async def test_resolve_returns_cached_value_without_db(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(url_service, "get_from_cache", AsyncMock(return_value="https://cached.example"))
    monkeypatch.setattr(url_service, "set_in_cache", AsyncMock())

    result = await url_service.resolve_short_code("abc1234")

    assert result == "https://cached.example"
    db.urls.find_one.assert_not_awaited()


async def test_resolve_cache_miss_hits_db_and_populates_cache(monkeypatch):
    db = _fake_db()
    db.urls.find_one.return_value = {
        "short_code": "abc1234",
        "long_url": "https://db.example",
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        "is_active": True,
    }
    set_cache = AsyncMock()
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(url_service, "get_from_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(url_service, "set_in_cache", set_cache)

    result = await url_service.resolve_short_code("abc1234")

    assert result == "https://db.example"
    set_cache.assert_awaited_once()
    db.urls.update_one.assert_awaited_once()


async def test_resolve_returns_none_when_not_found(monkeypatch):
    db = _fake_db()
    db.urls.find_one.return_value = None
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(url_service, "get_from_cache", AsyncMock(return_value=None))

    assert await url_service.resolve_short_code("missing") is None


async def test_resolve_returns_none_when_expired(monkeypatch):
    db = _fake_db()
    db.urls.find_one.return_value = {
        "short_code": "old",
        "long_url": "https://old.example",
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
        "is_active": True,
    }
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(url_service, "get_from_cache", AsyncMock(return_value=None))

    assert await url_service.resolve_short_code("old") is None
