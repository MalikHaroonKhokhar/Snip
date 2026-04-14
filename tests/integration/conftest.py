from datetime import datetime, timedelta, timezone

import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings


TEST_DB_NAME = f"{settings.mongo_db_name}_test"


@pytest_asyncio.fixture
async def test_db():
    """Isolated test database — dropped before and after each test."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    await client.drop_database(TEST_DB_NAME)
    db = client[TEST_DB_NAME]
    await db.urls.create_index("short_code", unique=True)
    await db.urls.create_index("expires_at", expireAfterSeconds=0)
    try:
        yield db
    finally:
        await client.drop_database(TEST_DB_NAME)
        client.close()


def make_doc(short_code: str = "abc1234", **overrides) -> dict:
    now = datetime.now(timezone.utc)
    base = {
        "short_code": short_code,
        "long_url": "https://example.com",
        "created_at": now,
        "expires_at": now + timedelta(days=30),
        "hits": 0,
        "is_active": True,
    }
    base.update(overrides)
    return base
