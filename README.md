# Snip — URL Shortener

A production-grade URL shortener built with FastAPI, MongoDB Atlas, and Upstash Redis. Designed for ~30M URL creations/month.

## Stack

- **API:** FastAPI + Uvicorn (Python 3.11+)
- **Database:** MongoDB Atlas (Motor async driver), TTL index on `expires_at`
- **Cache:** Upstash Redis (read-through + write-through)
- **Rate limiting:** SlowAPI (10/minute per IP on `POST /shorten`)
- **Background cleanup:** APScheduler (invalidates expired cache entries)
- **Encoding:** Base62, 7-char random short codes (`secrets`-backed)

## Architecture

```
POST /shorten ──► Base62 code ──► Mongo insert ──► Redis SETEX (write-through)
                                                         │
                                                         ▼
                                                  { short_url }

GET /{code} ──► Redis GET ──HIT──► 301 redirect
                    │
                    MISS
                    │
                    ▼
                Mongo find_one ──not found──► 404
                    │
                    found
                    ▼
                Redis SETEX ──► $inc hits ──► 301 redirect
```

Expiry is handled by MongoDB's native TTL index. A 5-min APScheduler sweep invalidates just-expired Redis entries and flips `is_active=False`.

## Local development

### 1. Environment
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill with real MONGO_URI + UPSTASH_REDIS_URL
```

### 2. Verify external connections
```bash
python scripts/check_connections.py
# [OK]  MongoDB OK (db=Snip)
# [OK]  Redis OK
```

### 3. Run the API + UI
```bash
uvicorn app.main:app --reload
# Web UI:      http://localhost:8000
# Health:      http://localhost:8000/health
# OpenAPI:     http://localhost:8000/docs
```

## API

| Method | Path        | Purpose                                   |
|--------|-------------|-------------------------------------------|
| GET    | `/`         | Minimal web UI to create a short link     |
| POST   | `/shorten`  | Create a short URL (rate-limited)         |
| GET    | `/{code}`   | 301 redirect to the long URL              |
| GET    | `/health`   | Liveness probe (returns `{"status":"ok"}`)|

### POST /shorten
```bash
curl -X POST http://localhost:8000/shorten \
  -H 'Content-Type: application/json' \
  -d '{"long_url":"https://example.com/very/long/path"}'
```

Response:
```json
{
  "short_url": "https://snip.onrender.com/aB3xY9z",
  "short_code": "aB3xY9z",
  "long_url": "https://example.com/very/long/path",
  "expires_at": "2026-05-14T12:00:00Z"
}
```

## Tests

```bash
pytest              # full suite
pytest -m unit      # pure, no I/O
pytest -m integration   # real MongoDB + Upstash
pytest -m e2e       # FastAPI TestClient with mocked services
```

Layout:
```
tests/
├── unit/           # models, encoder, url_service, cache_service, cleanup_service
├── integration/    # Atlas schema + indexes, cache roundtrip, cleanup job
└── e2e/            # /health, /shorten, /{code}, cache hit/miss, rate-limit bursts
```

## Deployment (Render)

`render.yaml` is committed — on Render:

1. **New → Blueprint** → connect this repo → Render reads `render.yaml`.
2. In the service's **Environment** tab, fill in the `sync: false` secrets:
   - `MONGO_URI` — Atlas SRV connection string with db user credentials
   - `UPSTASH_REDIS_URL` — starts with `rediss://`
   - `BASE_URL` — set to the deployed Render URL after the first deploy
3. In **MongoDB Atlas → Network Access**, allow `0.0.0.0/0` (Render's IPs are dynamic on the free tier).
4. Deploy. `/health` is the health check path; a green deploy means it's live.

Verify:
```bash
curl https://<your>.onrender.com/health
curl -X POST https://<your>.onrender.com/shorten \
  -H 'Content-Type: application/json' \
  -d '{"long_url":"https://google.com"}'
```

Docker is also supported — `Dockerfile` binds to `$PORT` for Render's dynamic port assignment.

## Configuration

All runtime config is env-driven (`app/config.py`, loaded from `.env` locally or platform env on Render):

| Variable              | Default      | Purpose                                  |
|-----------------------|--------------|------------------------------------------|
| `MONGO_URI`           | —            | Atlas SRV connection string              |
| `MONGO_DB_NAME`       | `Snip`       | Database name                            |
| `UPSTASH_REDIS_URL`   | —            | `rediss://...` TLS endpoint              |
| `BASE_URL`            | —            | Prefix for returned short URLs           |
| `CACHE_TTL_SECONDS`   | `3600`       | Redis key TTL                            |
| `DEFAULT_EXPIRY_DAYS` | `30`         | Default URL lifetime                     |
| `RATE_LIMIT`          | `10/minute`  | SlowAPI limit on `POST /shorten`         |

## CI

`.github/workflows/ci.yml` runs the unit suite on every push / PR to `main`. Integration and e2e tests are skipped in CI since they require live Mongo + Upstash credentials.
