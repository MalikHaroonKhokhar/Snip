# OUD-8.3 — Core API Endpoints

## Objective
Implement the two core endpoints of the URL shortener: `POST /shorten` and `GET /{code}`. These are the heart of the system — every architectural decision (Base62 encoding, DB write, cache check, redirect flow) runs through here.

---

## Endpoint 1: POST /shorten

### Route: app/routes/shorten.py

```python
from fastapi import APIRouter, Request, HTTPException
from app.models.url_model import ShortenRequest, ShortenResponse
from app.services.url_service import create_short_url
from app.config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.post("/shorten", response_model=ShortenResponse)
@limiter.limit(settings.rate_limit)
async def shorten_url(request: Request, body: ShortenRequest):
    result = await create_short_url(body)
    return result
```

### Flow
```
Client POST /shorten { long_url }
        ↓
Validate URL format (Pydantic HttpUrl)
        ↓
Generate Base62 short_code (7 chars)
        ↓
Check if short_code exists in DB (collision check)
  → If collision: regenerate (max 3 retries)
        ↓
Save to MongoDB { short_code, long_url, created_at, expires_at, hits=0 }
        ↓
Write to Upstash Redis cache (write-through)
        ↓
Return { short_url, short_code, long_url, expires_at }
```

### Request / Response

**Request:**
```json
POST /shorten
{
  "long_url": "https://example.com/very/long/path"
}
```

**Response 200:**
```json
{
  "short_url": "https://your-domain.onrender.com/aB3xY9z",
  "short_code": "aB3xY9z",
  "long_url": "https://example.com/very/long/path",
  "expires_at": "2026-05-14T00:00:00Z"
}
```

**Error 400** — Invalid URL format  
**Error 422** — Pydantic validation failure  
**Error 429** — Rate limit exceeded (slowapi)  
**Error 500** — DB write failure

---

## Endpoint 2: GET /{code}

### Route: app/routes/redirect.py

```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from app.services.url_service import resolve_short_code

router = APIRouter()

@router.get("/{code}")
async def redirect_url(code: str):
    long_url = await resolve_short_code(code)
    if not long_url:
        raise HTTPException(status_code=404, detail="Short URL not found or expired")
    return RedirectResponse(url=long_url, status_code=301)
```

### Flow (matches your notebook diagram exactly)
```
Client GET /{code}
        ↓
Extract short_code from path
        ↓
Validate code format (7 chars, alphanumeric)
        ↓
Check Upstash Redis cache
  → Cache HIT: return long_url immediately (no DB call)
  → Cache MISS:
        ↓
    Query MongoDB by short_code
      → Not found: return 404
      → Found but expired / inactive: return 404
      → Found: populate cache (read-through), increment hits
        ↓
HTTP 301 Redirect to long_url
```

### Why HTTP 301 vs 302?
- **301 (Permanent):** Browser caches the redirect — faster for repeat visits, reduces server load. Used here since short URLs don't change once created.
- **302 (Temporary):** Browser always hits the server — better if you need analytics on every visit. Can be made configurable.

---

## URL Service — app/services/url_service.py

```python
from datetime import datetime, timedelta
from app.db.mongo import get_db
from app.services.cache_service import get_from_cache, set_in_cache
from app.utils.encoder import generate_short_code
from app.models.url_model import ShortenRequest, ShortenResponse, URLDocument
from app.config import settings
from pymongo.errors import DuplicateKeyError

async def create_short_url(body: ShortenRequest) -> ShortenResponse:
    db = get_db()
    long_url = str(body.long_url)
    expiry_days = body.expiry_days or settings.default_expiry_days
    expires_at = datetime.utcnow() + timedelta(days=expiry_days)

    for attempt in range(3):
        short_code = generate_short_code()
        doc = {
            "short_code": short_code,
            "long_url": long_url,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
            "hits": 0,
            "is_active": True
        }
        try:
            await db.urls.insert_one(doc)
            # Write-through cache: write to Redis immediately after DB write
            await set_in_cache(short_code, long_url, ttl=settings.cache_ttl_seconds)
            break
        except DuplicateKeyError:
            if attempt == 2:
                raise Exception("Failed to generate unique short code after 3 attempts")
            continue

    return ShortenResponse(
        short_url=f"{settings.base_url}/{short_code}",
        short_code=short_code,
        long_url=long_url,
        expires_at=expires_at
    )

async def resolve_short_code(code: str) -> str | None:
    # 1. Check cache first (read-through pattern)
    cached = await get_from_cache(code)
    if cached:
        return cached

    # 2. Cache miss — query DB
    db = get_db()
    doc = await db.urls.find_one({"short_code": code, "is_active": True})
    if not doc:
        return None

    # 3. Check expiry (belt + suspenders — TTL index handles DB, this handles edge cases)
    if doc["expires_at"] < datetime.utcnow():
        return None

    # 4. Populate cache (read-through) + increment hit counter async
    await set_in_cache(code, doc["long_url"], ttl=settings.cache_ttl_seconds)
    await db.urls.update_one({"short_code": code}, {"$inc": {"hits": 1}})

    return doc["long_url"]
```

---

## Base62 Encoder — app/utils/encoder.py

```python
import random
import string

BASE62_CHARS = string.ascii_letters + string.digits  # A-Z, a-z, 0-9 = 62 chars
SHORT_CODE_LENGTH = 7  # 62^7 = 3.5 trillion combinations

def generate_short_code(length: int = SHORT_CODE_LENGTH) -> str:
    """
    Generates a random 7-character Base62 string.
    62^7 = 3,521,614,606,208 possible combinations.
    Sufficient for 1.8B URLs (6 years × 30M/month) with negligible collision rate.
    """
    return ''.join(random.choices(BASE62_CHARS, k=length))
```

**Why Base62 over MD5?**
- MD5 produces 128-bit hash → truncated to 7 chars loses uniqueness guarantees
- Base62 random generation is simpler, faster, and collision-resistant at this scale
- Shortened links are **not predictable** (non-sequential) — satisfies non-functional requirement

---

## Acceptance Criteria
- [ ] `POST /shorten` with valid URL returns 200 + short URL
- [ ] `POST /shorten` with invalid URL returns 422
- [ ] `GET /{code}` with valid code returns 301 redirect
- [ ] `GET /{code}` with unknown code returns 404
- [ ] `GET /{code}` with expired code returns 404
- [ ] Short code is exactly 7 alphanumeric characters
- [ ] Duplicate short_code collision is handled with retry (max 3 attempts)
- [ ] Cache is populated on both write (POST) and read miss (GET)
