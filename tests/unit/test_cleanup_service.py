from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import cleanup_service


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _AsyncCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


def _fake_db(docs):
    db = MagicMock()
    db.urls.find = MagicMock(return_value=_AsyncCursor(docs))
    db.urls.update_one = AsyncMock()
    return db


async def test_cleanup_invalidates_cache_and_soft_deletes(monkeypatch):
    docs = [
        {"short_code": "aaa1111", "is_active": True},
        {"short_code": "bbb2222", "is_active": True},
    ]
    db = _fake_db(docs)
    delete = AsyncMock()
    monkeypatch.setattr(cleanup_service, "get_db", lambda: db)
    monkeypatch.setattr(cleanup_service, "delete_from_cache", delete)

    count = await cleanup_service.cleanup_expired_urls()

    assert count == 2
    assert delete.await_count == 2
    assert {c.args[0] for c in delete.call_args_list} == {"aaa1111", "bbb2222"}
    assert db.urls.update_one.await_count == 2
    # each soft-delete flips is_active to False
    for call in db.urls.update_one.call_args_list:
        assert call.args[1] == {"$set": {"is_active": False}}


async def test_cleanup_returns_zero_when_no_expired(monkeypatch):
    db = _fake_db([])
    monkeypatch.setattr(cleanup_service, "get_db", lambda: db)
    monkeypatch.setattr(cleanup_service, "delete_from_cache", AsyncMock())

    assert await cleanup_service.cleanup_expired_urls() == 0


async def test_cleanup_skips_when_db_not_initialised(monkeypatch):
    monkeypatch.setattr(cleanup_service, "get_db", lambda: None)

    assert await cleanup_service.cleanup_expired_urls() == 0


async def test_cleanup_queries_recent_expiry_window(monkeypatch):
    db = _fake_db([])
    monkeypatch.setattr(cleanup_service, "get_db", lambda: db)
    monkeypatch.setattr(cleanup_service, "delete_from_cache", AsyncMock())

    await cleanup_service.cleanup_expired_urls()

    query = db.urls.find.call_args.args[0]
    assert query["is_active"] is True
    assert "$gte" in query["expires_at"] and "$lte" in query["expires_at"]


async def test_start_and_stop_scheduler_registers_job():
    cleanup_service.start_cleanup_scheduler(interval_minutes=1)
    try:
        assert cleanup_service.scheduler.running
        job = cleanup_service.scheduler.get_job("url_cleanup")
        assert job is not None
        assert job.trigger.interval.total_seconds() == 60
    finally:
        cleanup_service.stop_cleanup_scheduler()
