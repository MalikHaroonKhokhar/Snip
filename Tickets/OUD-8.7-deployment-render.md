# OUD-8.7 — Deployment to Render

## Objective
Deploy the URL shortener to Render (free tier) so it is publicly accessible. The service must pass all acceptance criteria in a live environment, not just locally.

---

## Deployment Target
- **Platform:** Render (render.com)
- **Service Type:** Web Service (not static site)
- **Runtime:** Python 3.11
- **Plan:** Free tier
- **Region:** Oregon (US West) — lowest latency for most users

---

## Option A: Render Native (No Docker) — Recommended for Simplicity

### render.yaml (infrastructure as code)

```yaml
services:
  - type: web
    name: url-shortener
    runtime: python
    region: oregon
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: MONGO_URI
        sync: false          # Set manually in Render dashboard
      - key: MONGO_DB_NAME
        value: urlshortener
      - key: UPSTASH_REDIS_URL
        sync: false          # Set manually in Render dashboard
      - key: BASE_URL
        sync: false          # Set to your Render URL after first deploy
      - key: CACHE_TTL_SECONDS
        value: "3600"
      - key: DEFAULT_EXPIRY_DAYS
        value: "30"
      - key: RATE_LIMIT
        value: "10/minute"
```

---

## Option B: Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app/ ./app/

# Expose port (Render sets $PORT dynamically)
EXPOSE 8000

# Start with uvicorn — bind to 0.0.0.0 so Render can reach it
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Note:** On Render, use `$PORT` env var — Render assigns the port dynamically:
```dockerfile
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

---

## Deployment Steps

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial URL shortener implementation"
git remote add origin https://github.com/your-username/url-shortener.git
git push -u origin main
```

**CRITICAL: Verify `.gitignore` excludes `.env` before pushing.**

### Step 2 — Create Render Web Service
1. Go to [render.com](https://render.com) → New → Web Service
2. Connect your GitHub repo
3. Configure:
   - **Name:** `url-shortener`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Step 3 — Set Environment Variables in Render Dashboard
Go to Environment tab and add:
```
MONGO_URI          = mongodb+srv://...  (from Atlas)
UPSTASH_REDIS_URL  = rediss://...       (from Upstash console)
BASE_URL           = https://url-shortener.onrender.com  (after first deploy)
MONGO_DB_NAME      = urlshortener
CACHE_TTL_SECONDS  = 3600
DEFAULT_EXPIRY_DAYS = 30
RATE_LIMIT         = 10/minute
```

### Step 4 — Verify Deployment
After deploy completes:
```bash
# Health check
curl https://url-shortener.onrender.com/health
# Expected: {"status": "ok"}

# Test shortening
curl -X POST https://url-shortener.onrender.com/shorten \
  -H "Content-Type: application/json" \
  -d '{"long_url": "https://google.com"}'

# Test redirect (follow redirect)
curl -L https://url-shortener.onrender.com/{short_code}
```

---

## Render Free Tier Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Spins down after 15min inactivity | Cold start ~30s | Acceptable for demo/simplified build |
| 512MB RAM | Sufficient for FastAPI + Motor | Monitor in Render dashboard |
| Shared CPU | Slower under load | Adequate for simplified build |
| 750 hours/month | Enough for 1 service | Free tier covers it |

**Cold start note:** On first request after spin-down, MongoDB connection re-establishes. The `startup` event handler in `main.py` handles this. Redis reconnects lazily on first cache operation.

---

## Health Check Endpoint

Already implemented in OUD-8.1:
```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

Render uses `/health` to determine if the service is up. If it returns non-200, Render marks the deploy as failed.

---

## Acceptance Criteria
- [ ] Service deploys successfully on Render (green deploy status)
- [ ] `GET /health` returns 200 from public Render URL
- [ ] `POST /shorten` works from public URL
- [ ] `GET /{code}` redirects correctly from public URL
- [ ] All environment variables are set in Render dashboard (not in code)
- [ ] `.env` file is NOT committed to Git
- [ ] MongoDB Atlas connection works from Render's IP (whitelist `0.0.0.0/0` in Atlas Network Access for simplified build)
- [ ] Upstash Redis connection works from Render
- [ ] `BASE_URL` is updated to the actual Render domain after first deploy
