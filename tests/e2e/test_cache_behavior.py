"""End-to-end checks of cache-aware redirect flow, with Mongo + Redis both mocked.

Asserts the two architectural guarantees from OUD-8.4:
  1. Cache HIT must NOT touch MongoDB.
  2. Redis failure must NOT surface as 500 — fall through to DB silently.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import url_service


pytestmark = pytest.mark.e2e


@pytest.fixture
def client():
    return TestClient(app)


def _fake_db(doc=None):
    db = MagicMock()
    db.urls.find_one = AsyncMock(return_value=doc)
    db.urls.update_one = AsyncMock()
    return db


def test_cache_hit_skips_mongo(client, monkeypatch):
    db = _fake_db(doc={"should": "not be read"})
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    monkeypatch.setattr(
        url_service, "get_from_cache", AsyncMock(return_value="https://cached.example")
    )
    set_cache = AsyncMock()
    monkeypatch.setattr(url_service, "set_in_cache", set_cache)

    resp = client.get("/abc1234", follow_redirects=False)

    assert resp.status_code == 301
    assert resp.headers["location"] == "https://cached.example"
    db.urls.find_one.assert_not_awaited()
    set_cache.assert_not_awaited()


def test_redis_failure_falls_through_to_db(client, monkeypatch):
    doc = {
        "short_code": "abc1234",
        "long_url": "https://db.example",
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        "is_active": True,
    }
    db = _fake_db(doc=doc)
    monkeypatch.setattr(url_service, "get_db", lambda: db)
    # get_from_cache returns None on any failure (per cache_service contract),
    # so resolve_short_code should silently fall through to DB.
    monkeypatch.setattr(url_service, "get_from_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(url_service, "set_in_cache", AsyncMock())

    resp = client.get("/abc1234", follow_redirects=False)

    assert resp.status_code == 301
    assert resp.headers["location"] == "https://db.example"
    db.urls.find_one.assert_awaited_once()
