# OUD-8.4 — Redis Caching (Upstash)

## Objective
Implement read-through and write-through caching using Upstash Redis to minimize DB hits on redirects. Redirects must happen in real-time with minimal latency — this is the core non-functional requirement.

---

## Why Upstash?
- Serverless Redis — no infrastructure to manage
- Free tier: 10,000 commands/day, 256MB storage
- HTTP-based connection — works on Render's free tier (no persistent TCP required)
- Pay-per-use after free tier — scales naturally

---

## Cache Architecture

### Two Patterns in Use

**Read-Through Cache (on GET /{code}):**
```
Request → Check Redis
  HIT  → Return long_url immediately (no DB touch)
  MISS → Query MongoDB → Store in Redis → Return long_url
```

**Write-Through Cache (on POST /shorten):**
```
POST → Write to MongoDB → Write to Redis simultaneously
```
Write-through ensures the cache is warm immediately after creation. The first redirect after a new short URL is created will always hit cache, not DB.

---

## Cache Service — app/services/cache_service.py

```python
import redis.asyncio as redis
from app.config import settings

_redis_client: redis.Redis = None

async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.upstash_redis_url,
            decode_responses=True,
            ssl=True  # Upstash requires TLS (rediss://)
        )
    return _redis_client

async def get_from_cache(short_code: str) -> str | None:
    """
    Read-through: check cache before DB.
    Returns long_url string or None on miss.
    """
    try:
        client = await get_redis()
        return await client.get(f"url:{short_code}")
    except Exception as e:
        # Cache failure must NEVER break the redirect flow
        print(f"[Cache] GET failed for {short_code}: {e}")
        return None

async def set_in_cache(short_code: str, long_url: str, ttl: int) -> None:
    """
    Write-through: populate cache on both create and cache miss.
    TTL matches URL expiry to prevent stale cache entries.
    """
    try:
        client = await get_redis()
        await client.setex(f"url:{short_code}", ttl, long_url)
    except Exception as e:
        # Cache failure on write is non-fatal — DB is source of truth
        print(f"[Cache] SET failed for {short_code}: {e}")

async def delete_from_cache(short_code: str) -> None:
    """
    Called by cleanup service when manually invalidating an expired URL.
    """
    try:
        client = await get_redis()
        await client.delete(f"url:{short_code}")
    except Exception as e:
        print(f"[Cache] DELETE failed for {short_code}: {e}")
```

---

## Key Design Decisions

### Key Naming Convention
```
url:{short_code}  →  e.g., url:aB3xY9z
```
Namespaced with `url:` prefix to avoid collisions if Redis is shared with other services in future.

### TTL Strategy
- Cache TTL = `CACHE_TTL_SECONDS` (default: 3600 = 1 hour)
- This should be ≤ URL expiry duration
- When URL expires in DB (via TTL index), the cache entry also expires naturally
- No stale cache problem — both DB and cache TTLs are aligned

### Failure Isolation
- **Cache miss is not an error** — fall through to DB silently
- **Cache write failure is non-fatal** — DB is always the source of truth
- **Cache read failure is non-fatal** — log and fall through to DB
- Redis going down must NOT take down the redirect service

---

## Cache Flow Diagram

```
GET /{code}
    │
    ▼
Redis GET url:{code}
    │
    ├── HIT ──────────────────────→ 301 Redirect (fast path, ~1ms)
    │
    └── MISS
          │
          ▼
       MongoDB find_one(short_code)
          │
          ├── Not Found ──────────→ 404
          │
          └── Found
                │
                ▼
           Redis SETEX url:{code} TTL long_url   ← populate cache
                │
                ▼
           MongoDB $inc hits +1   ← async counter
                │
                ▼
           301 Redirect (cold path, ~10-50ms)
```

---

## Environment Variable Required

```
UPSTASH_REDIS_URL=rediss://:your-password@your-host.upstash.io:6379
```

Note: `rediss://` (with double s) = TLS-encrypted connection. Required by Upstash.

---

## Testing Cache Behavior

```python
# In test_main.py — mock Redis for unit tests
from unittest.mock import AsyncMock, patch

@patch("app.services.cache_service.get_redis")
async def test_cache_hit(mock_redis):
    mock_client = AsyncMock()
    mock_client.get.return_value = "https://example.com"
    mock_redis.return_value = mock_client

    # GET /{code} should return redirect without hitting DB
    response = await client.get("/aB3xY9z")
    assert response.status_code == 301
    mock_client.get.assert_called_once_with("url:aB3xY9z")
```

---

## Acceptance Criteria
- [ ] `GET /{code}` on cached code does NOT query MongoDB
- [ ] `POST /shorten` populates Redis immediately (write-through)
- [ ] Cache miss falls through to MongoDB correctly
- [ ] Redis failure does NOT cause 500 — fallback to DB silently
- [ ] Cache key format is `url:{short_code}`
- [ ] TLS connection (`rediss://`) is used for Upstash
- [ ] Cache TTL is configurable via `.env` (`CACHE_TTL_SECONDS`)
- [ ] Expired URL cache entries auto-expire (TTL aligned with URL expiry)
