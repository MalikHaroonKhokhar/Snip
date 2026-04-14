import pytest
from pymongo.errors import DuplicateKeyError

from app.db import mongo as mongo_module
from .conftest import make_doc


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_connect_db_creates_indexes_and_returns_db():
    db = await mongo_module.connect_db()
    try:
        assert db is not None
        assert mongo_module.get_db() is db

        indexes = await db.urls.index_information()
        short_code_idx = next(
            (v for v in indexes.values() if v["key"] == [("short_code", 1)]),
            None,
        )
        expires_idx = next(
            (v for v in indexes.values() if v["key"] == [("expires_at", 1)]),
            None,
        )
        assert short_code_idx is not None and short_code_idx.get("unique") is True
        assert expires_idx is not None and expires_idx.get("expireAfterSeconds") == 0
    finally:
        await mongo_module.close_db()


async def test_close_db_clears_global_handles():
    await mongo_module.connect_db()
    await mongo_module.close_db()
    assert mongo_module.get_db() is None


async def test_unique_short_code_raises_duplicate_key(test_db):
    await test_db.urls.insert_one(make_doc("dupcode"))
    with pytest.raises(DuplicateKeyError):
        await test_db.urls.insert_one(make_doc("dupcode"))


async def test_ttl_index_present_on_test_db(test_db):
    indexes = await test_db.urls.index_information()
    ttl = next(
        (v for v in indexes.values() if v["key"] == [("expires_at", 1)]),
        None,
    )
    assert ttl is not None
    assert ttl.get("expireAfterSeconds") == 0
