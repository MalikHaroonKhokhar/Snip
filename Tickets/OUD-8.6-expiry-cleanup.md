# OUD-8.6 — Expiry & Cleanup Service

## Objective
Implement URL expiry and cleanup to free storage and prevent stale redirects. Two mechanisms work together: MongoDB's native TTL index (primary) and a background cleanup scheduler (secondary, for cache invalidation and soft-deleted records).

---

## Two-Layer Cleanup Architecture

### Layer 1 — MongoDB TTL Index (Automatic)
MongoDB's background thread checks the `expires_at` field every ~60 seconds and auto-deletes expired documents. This was set up in OUD-8.2:

```python
await db.urls.create_index("expires_at", expireAfterSeconds=0)
```

**What this handles:**
- Auto-deletes expired URL documents from MongoDB
- No application code needed
- Runs at DB level — always active even if app is down

**Limitation:** Does NOT invalidate the Redis cache. A URL could be deleted from DB but still cached in Redis until TTL expires naturally.

### Layer 2 — Background Scheduler (Cache Invalidation)
A lightweight APScheduler job runs periodically to find recently-expired URLs still in Redis and explicitly delete their cache entries.

---

## Implementation — app/services/cleanup_service.py

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from app.db.mongo import get_db
from app.services.cache_service import delete_from_cache

scheduler = AsyncIOScheduler()

async def cleanup_expired_urls():
    """
    Runs on schedule to:
    1. Find URLs that expired in the last cleanup window
    2. Explicitly delete their Redis cache entries
    3. Mark them as inactive (soft delete) if not already removed by TTL index
    """
    db = get_db()
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=10)  # Look back 10 min

    # Find recently expired documents (TTL index may not have fired yet)
    cursor = db.urls.find({
        "expires_at": {"$gte": window_start, "$lte": now},
        "is_active": True
    })

    count = 0
    async for doc in cursor:
        short_code = doc["short_code"]
        # Invalidate Redis cache immediately
        await delete_from_cache(short_code)
        # Soft delete (TTL index will hard delete, this just marks it)
        await db.urls.update_one(
            {"short_code": short_code},
            {"$set": {"is_active": False}}
        )
        count += 1

    if count > 0:
        print(f"[Cleanup] Invalidated {count} expired URL(s) from cache")

def start_cleanup_scheduler():
    """
    Called on app startup. Runs cleanup every 5 minutes.
    """
    scheduler.add_job(
        cleanup_expired_urls,
        trigger="interval",
        minutes=5,
        id="url_cleanup",
        replace_existing=True
    )
    scheduler.start()
    print("[Cleanup] Scheduler started — running every 5 minutes")
```

Add `apscheduler` to requirements.txt:
```
apscheduler==3.10.4
```

---

## Expiry Logic in URL Creation (from OUD-8.3)

```python
expiry_days = body.expiry_days or settings.default_expiry_days
expires_at = datetime.utcnow() + timedelta(days=expiry_days)
```

Default: 30 days (configurable via `DEFAULT_EXPIRY_DAYS` in `.env`).

---

## Expiry Check on Redirect (belt + suspenders)

In `url_service.py → resolve_short_code()`, even after a cache miss and DB hit, we validate:

```python
if doc["expires_at"] < datetime.utcnow():
    return None  # Return 404 even if doc exists
```

This covers the edge case where the TTL index hasn't fired yet (MongoDB checks every ~60s, so there's a small window where an expired document is still retrievable).

---

## Cleanup Flow Summary

```
URL Created → expires_at set (now + 30 days)
                    │
                    ▼
           [MongoDB TTL Index]
           Checks every ~60 seconds
           Deletes doc when expires_at < now
                    │
           [APScheduler — every 5 min]
           Finds about-to-expire / just-expired URLs
           Deletes their Redis cache entries
           Marks is_active = False
                    │
                    ▼
           Redirect returns 404 for expired codes
```

---

## Storage Impact (from architecture notes)

Without cleanup:
- 30M URLs/month × 2.031KB = ~60.78 GB/month accumulation
- After 6 years: 3.64 TB

With 30-day expiry + TTL cleanup:
- Active storage stays bounded to ~30 days × 60.78 GB = ~1.82 TB max
- Expired documents removed automatically — no manual maintenance

---

## Acceptance Criteria
- [ ] APScheduler starts on app startup without blocking the event loop
- [ ] Cleanup job runs every 5 minutes (configurable)
- [ ] Expired URLs are removed from Redis cache by cleanup job
- [ ] `is_active` is set to `False` on expired URLs by cleanup job
- [ ] MongoDB TTL index auto-deletes expired documents (verify in Atlas UI)
- [ ] `GET /{code}` returns 404 for expired URL even before TTL index fires
- [ ] Cleanup job logs count of invalidated entries
- [ ] Scheduler shuts down cleanly on app shutdown (no hanging threads)
