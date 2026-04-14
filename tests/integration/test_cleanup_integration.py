from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.services import cleanup_service
from .conftest import make_doc


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_cleanup_finds_recent_expired_docs_and_soft_deletes(test_db, monkeypatch):
    now = cleanup_service._utcnow()
    # Seed: one just-expired (2 min ago), one still active, one expired long ago.
    just_expired = make_doc("exprecent", expires_at=now - timedelta(minutes=2))
    active = make_doc("stillgood", expires_at=now + timedelta(days=5))
    long_ago = make_doc("expirold", expires_at=now - timedelta(hours=2))
    await test_db.urls.insert_many([just_expired, active, long_ago])

    delete_cache = AsyncMock()
    monkeypatch.setattr(cleanup_service, "get_db", lambda: test_db)
    monkeypatch.setattr(cleanup_service, "delete_from_cache", delete_cache)

    count = await cleanup_service.cleanup_expired_urls()

    assert count == 1
    delete_cache.assert_awaited_once_with("exprecent")

    # Only the just-expired doc was soft-deleted.
    got = {d["short_code"]: d["is_active"] for d in await test_db.urls.find().to_list(None)}
    assert got["exprecent"] is False
    assert got["stillgood"] is True
    assert got["expirold"] is True  # outside lookback window — untouched
