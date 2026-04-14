# Snip

A fast, self-contained URL shortener. Paste a long link, get a short one that redirects.

**Live:** https://snip-6gqo.onrender.com/

---

## Highlights

- **FastAPI** backend with an inline web UI at `/`
- **MongoDB Atlas** for durable storage, with a TTL index that auto-expires old URLs
- **Upstash Redis** for read-through + write-through caching — cold redirects hit the DB once, then the cache
- **SlowAPI** rate limiting on `POST /shorten` (IP-based, configurable)
- **APScheduler** background sweep to invalidate just-expired cache entries
- Short codes are 7-char Base62 from `secrets` — random, not enumerable
- Typed end-to-end via Pydantic; async all the way down (Motor + redis.asyncio)

## How it works

```
POST /shorten ──► Base62 code ──► Mongo insert ──► Redis SETEX   (write-through)
                                                         │
                                                         ▼
                                                  { short_url }

GET /{code}  ──► Redis GET ──HIT──► 301 redirect
                    │
                    MISS
                    │
                    ▼
                Mongo find_one ──not found──► 404
                    │
                    ▼
                Redis SETEX ──► $inc hits ──► 301 redirect
```

Expiry is enforced by MongoDB's native TTL index. A periodic scheduler sweeps recently-expired docs to proactively invalidate their Redis entries.

## API

| Method | Path        | Purpose                                   |
|--------|-------------|-------------------------------------------|
| GET    | `/`         | Web UI for creating a short link          |
| POST   | `/shorten`  | Create a short URL (rate-limited)         |
| GET    | `/{code}`   | 301 redirect to the long URL              |
| GET    | `/health`   | Liveness probe                            |
| GET    | `/docs`     | Interactive OpenAPI docs                  |

### Example

```bash
curl -X POST https://snip-6gqo.onrender.com/shorten \
  -H 'Content-Type: application/json' \
  -d '{"long_url":"https://example.com/very/long/path"}'
```

```json
{
  "short_url": "https://snip-6gqo.onrender.com/aB3xY9z",
  "short_code": "aB3xY9z",
  "long_url": "https://example.com/very/long/path",
  "expires_at": "2026-05-14T12:00:00Z"
}
```

Then `GET /aB3xY9z` → 301 to the long URL.

## Local development

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in MONGO_URI and UPSTASH_REDIS_URL
```

Verify your external services before running the app:

```bash
python scripts/check_connections.py
# [OK]  MongoDB OK (db=Snip)
# [OK]  Redis OK
```

Then:

```bash
uvicorn app.main:app --reload
# UI       http://localhost:8000
# Health   http://localhost:8000/health
# Docs     http://localhost:8000/docs
```

## Configuration

All config is env-driven (`app/config.py`):

| Variable              | Default      | Purpose                                   |
|-----------------------|--------------|-------------------------------------------|
| `MONGO_URI`           | —            | Atlas SRV connection string               |
| `MONGO_DB_NAME`       | `Snip`       | Database name                             |
| `UPSTASH_REDIS_URL`   | —            | `rediss://...` TLS endpoint               |
| `BASE_URL`            | —            | Prefix for returned short URLs            |
| `CACHE_TTL_SECONDS`   | `3600`       | Redis key TTL                             |
| `DEFAULT_EXPIRY_DAYS` | `30`         | Default URL lifetime                      |
| `RATE_LIMIT`          | `10/minute`  | SlowAPI limit on `POST /shorten`          |

## Tests

A three-tier suite, marker-selectable:

```bash
pytest                    # everything
pytest -m unit            # pure, no I/O
pytest -m integration     # real MongoDB + Upstash
pytest -m e2e             # FastAPI TestClient with mocked services
```

```
tests/
├── unit/           # models, encoder, url_service, cache_service, cleanup_service
├── integration/    # Atlas schema + indexes, cache roundtrip, cleanup sweep
└── e2e/            # /health, /shorten, /{code}, cache hit/miss, rate-limit bursts
```

## Deployment

Deployed on Render via `render.yaml` (Blueprint). The Dockerfile is also `$PORT`-aware if you prefer container deploys.

1. **New → Blueprint** on Render, connect this repo. Render reads `render.yaml`.
2. In the service's **Environment** tab, supply the three `sync: false` secrets:
   - `MONGO_URI`
   - `UPSTASH_REDIS_URL`
   - `BASE_URL` — set to the deployed URL after first deploy, then redeploy
3. In **MongoDB Atlas → Network Access**, allow `0.0.0.0/0` (Render free-tier IPs are dynamic).
4. `/health` is the health check path; a green deploy means it's live.

## Project layout

```
app/
├── main.py                    # FastAPI app, lifespan, routes mount
├── config.py                  # env-backed Settings
├── routes/
│   ├── shorten.py             # POST /shorten (rate-limited)
│   └── redirect.py            # GET /{code}
├── services/
│   ├── url_service.py         # create + resolve (cache/db orchestration)
│   ├── cache_service.py       # Redis read-through / write-through
│   └── cleanup_service.py     # APScheduler expiry sweeper
├── db/mongo.py                # Motor client + index setup
├── models/url_model.py        # Pydantic request/response/document
├── utils/encoder.py           # Base62 short-code generator
└── static/index.html          # minimal web UI
```

## CI

`.github/workflows/ci.yml` runs the unit suite on every push / PR to `main`. Integration and e2e tests are skipped in CI since they need live Mongo + Upstash credentials.
