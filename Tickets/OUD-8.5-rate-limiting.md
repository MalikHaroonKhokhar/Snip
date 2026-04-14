# OUD-8.5 — Rate Limiting on POST /shorten

## Objective
Protect the `POST /shorten` endpoint from abuse, DDoS attacks, and spam URL creation using IP-based rate limiting via SlowAPI (FastAPI-native). This satisfies both the acceptance criteria and the Security architectural requirement from the system design.

---

## Why Rate Limit Only POST /shorten?
- `GET /{code}` must be ultra-fast and unrestricted — it's the hot path
- `POST /shorten` is the resource-intensive path (DB write + cache write)
- Spammers could flood the DB with millions of short URLs without rate limiting
- Rate limiting POST protects storage capacity and prevents abuse

---

## Library: SlowAPI

SlowAPI is the FastAPI equivalent of Flask-Limiter. It integrates with FastAPI's middleware system and uses Redis (or in-memory) as a backend for distributed rate limit counters.

```
pip install slowapi
```

---

## Implementation

### app/main.py (rate limiter setup — already in OUD-8.1)

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)  # Rate limit by client IP
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

### app/routes/shorten.py (rate limit decorator)

```python
from fastapi import APIRouter, Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings
from app.models.url_model import ShortenRequest, ShortenResponse
from app.services.url_service import create_short_url

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.post("/shorten", response_model=ShortenResponse)
@limiter.limit(settings.rate_limit)  # e.g., "10/minute" from .env
async def shorten_url(request: Request, body: ShortenRequest):
    """
    POST /shorten
    Rate limited to RATE_LIMIT per IP per window.
    Default: 10 requests/minute.
    Returns 429 Too Many Requests on breach.
    """
    result = await create_short_url(body)
    return result
```

---

## Rate Limit Configuration

```
# .env
RATE_LIMIT=10/minute
```

**Supported formats:**
- `10/minute` — 10 requests per minute per IP
- `100/hour` — 100 requests per hour per IP
- `5/second` — 5 requests per second per IP

Default is `10/minute` — reasonable for a public shortener without auth.

---

## Response on Limit Exceeded

SlowAPI automatically returns:

```
HTTP 429 Too Many Requests
Content-Type: application/json

{
  "error": "Rate limit exceeded: 10 per 1 minute"
}
```

Headers returned:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1713096000
Retry-After: 47
```

---

## Security Context (from architecture notes)

This rate limiting is one layer of the security architecture:

| Threat | Mitigation |
|---|---|
| DDoS on POST | SlowAPI rate limiting by IP |
| Phishing links | URL validation (Pydantic HttpUrl) |
| Short code enumeration | Base62 random (non-sequential, non-predictable) |
| Cache poisoning | Cache keys namespaced, TTL enforced |

**Note:** For production at scale, rate limiting should be moved to the Load Balancer / API Gateway layer (e.g., Nginx, Cloudflare) so it runs before hitting the app server. For this simplified build, SlowAPI at the application layer is sufficient.

---

## Storage Backend for Rate Limit Counters

By default SlowAPI uses in-memory storage — this resets on server restart and doesn't work across multiple instances.

For this build (single Render instance), in-memory is fine. For multi-instance production:

```python
# Use Redis as rate limit backend (same Upstash instance)
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.upstash_redis_url  # Share Upstash with cache
)
```

---

## Acceptance Criteria
- [ ] `POST /shorten` returns 429 after exceeding `RATE_LIMIT` from same IP
- [ ] Response headers include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`
- [ ] `GET /{code}` is NOT rate limited
- [ ] Rate limit value is configurable via `.env` (not hardcoded)
- [ ] 429 response body matches SlowAPI standard format
- [ ] Rate limit does not block requests below the threshold
