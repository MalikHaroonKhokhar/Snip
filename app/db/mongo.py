from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

client: AsyncIOMotorClient | None = None
db: AsyncIOMotorDatabase | None = None


async def connect_db() -> AsyncIOMotorDatabase:
    global client, db
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]
    await client.admin.command("ping")
    await db.urls.create_index("short_code", unique=True)
    await db.urls.create_index("expires_at", expireAfterSeconds=0)
    return db


async def close_db() -> None:
    global client, db
    if client is not None:
        client.close()
        client = None
        db = None


def get_db() -> AsyncIOMotorDatabase | None:
    return db
