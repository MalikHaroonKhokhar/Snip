# OUD-8.2 — Database & Schema (MongoDB Atlas)

## Objective
Design and implement the MongoDB Atlas schema for URL storage. The DB must handle 30M URLs/month efficiently, support expiry-based cleanup, and use NoSQL's document flexibility for future analytics fields.

---

## Why NoSQL (MongoDB) over SQL
- URL mappings are simple key-value documents — no joins needed
- Schema flexibility allows adding analytics fields (click count, geo, device) later
- MongoDB Atlas free tier (512MB) is sufficient for the simplified build
- Horizontal scaling fits the eventual 1.8B record target (6 years × 30M/month)

---

## MongoDB Connection — app/db/mongo.py

```python
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client: AsyncIOMotorClient = None
db = None

async def connect_db():
    global client, db
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]
    # Create indexes on startup
    await db.urls.create_index("short_code", unique=True)
    await db.urls.create_index("expires_at", expireAfterSeconds=0)  # TTL index
    print("Connected to MongoDB Atlas")

async def close_db():
    global client
    if client:
        client.close()

def get_db():
    return db
```

---

## Document Schema

### Collection: `urls`

```json
{
  "_id": "ObjectId (auto)",
  "short_code": "aB3xY9z",
  "long_url": "https://some-very-long-url.com/path?query=value",
  "created_at": "ISODate",
  "expires_at": "ISODate (TTL index — MongoDB auto-deletes after this)",
  "hits": 0,
  "is_active": true
}
```

### Field Breakdown

| Field | Type | Purpose |
|---|---|---|
| `short_code` | String (7 chars) | Base62-encoded unique key — indexed, unique |
| `long_url` | String (max 2048 chars) | Original URL — 2KB avg as per capacity model |
| `created_at` | DateTime | Audit + analytics |
| `expires_at` | DateTime | TTL index — MongoDB deletes doc automatically |
| `hits` | Int | Click counter — incremented on every redirect |
| `is_active` | Bool | Soft delete / manual deactivation |

---

## Indexes

```python
# Unique index on short_code — fast O(1) lookups on redirect
await db.urls.create_index("short_code", unique=True)

# TTL index — MongoDB auto-deletes documents after expires_at
await db.urls.create_index("expires_at", expireAfterSeconds=0)
```

**Why TTL index?** Replaces the need for a heavy cleanup cron job. MongoDB's background thread checks every 60 seconds and removes expired documents automatically. This handles the "Cleanup Service" architectural requirement natively.

---

## Pydantic Models — app/models/url_model.py

```python
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime
from typing import Optional

class ShortenRequest(BaseModel):
    long_url: HttpUrl
    custom_code: Optional[str] = None  # Future: custom short codes
    expiry_days: Optional[int] = None  # Override default expiry

class ShortenResponse(BaseModel):
    short_url: str
    short_code: str
    long_url: str
    expires_at: datetime

class URLDocument(BaseModel):
    short_code: str
    long_url: str
    created_at: datetime
    expires_at: datetime
    hits: int = 0
    is_active: bool = True
```

---

## Capacity Validation (from architecture notes)

| Metric | Value |
|---|---|
| Avg long URL size | 2KB (2048 chars) |
| Short URL size | 17 bytes |
| created_at | 7 bytes |
| expires_at | 7 bytes |
| **Total per record** | ~2.031 KB |
| 30M records/month | ~60.78 GB/month |
| 6 years total | **~3.64 TB** |

MongoDB Atlas free tier handles the simplified build. Production would require M10+ cluster or sharding.

---

## Acceptance Criteria
- [ ] `connect_db()` establishes connection to Atlas on app startup
- [ ] `urls` collection has unique index on `short_code`
- [ ] TTL index on `expires_at` is created with `expireAfterSeconds=0`
- [ ] Inserting a duplicate `short_code` raises `DuplicateKeyError`
- [ ] All Pydantic models validate correctly (invalid URL rejected)
- [ ] `get_db()` returns the active database instance
