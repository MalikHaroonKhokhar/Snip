# OUD-8.1 — Project Setup & Scaffold

## Objective
Bootstrap the FastAPI project with a clean, production-ready folder structure. Every file, config, and dependency must be intentionally placed and explainable.

---

## Stack
- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Package Manager:** pip + `requirements.txt`
- **Environment Config:** `python-dotenv` via `.env` file

---

## Folder Structure to Create

```
url-shortener/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # Loads env vars via pydantic BaseSettings
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── shorten.py        # POST /shorten endpoint
│   │   └── redirect.py       # GET /{code} endpoint
│   ├── services/
│   │   ├── __init__.py
│   │   ├── url_service.py    # Core business logic
│   │   ├── cache_service.py  # Upstash Redis abstraction
│   │   └── cleanup_service.py# Background expiry task
│   ├── db/
│   │   ├── __init__.py
│   │   └── mongo.py          # MongoDB Atlas connection (Motor async driver)
│   ├── models/
│   │   ├── __init__.py
│   │   └── url_model.py      # Pydantic request/response models
│   └── utils/
│       ├── __init__.py
│       └── encoder.py        # Base62 encoding logic
├── tests/
│   └── test_main.py
├── .env                      # Never committed — secrets only
├── .env.example              # Committed — shows required keys without values
├── .gitignore
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## requirements.txt (exact packages)

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
motor==3.4.0              # async MongoDB driver
redis==5.0.4              # Upstash Redis client
python-dotenv==1.0.1
pydantic==2.7.1
pydantic-settings==2.2.1
slowapi==0.1.9            # Rate limiting
httpx==0.27.0             # For testing
pytest==8.2.0
pytest-asyncio==0.23.6
```

---

## .env.example

```
MONGO_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/urlshortener
MONGO_DB_NAME=urlshortener
UPSTASH_REDIS_URL=rediss://<password>@<host>.upstash.io:6379
BASE_URL=https://your-render-domain.onrender.com
CACHE_TTL_SECONDS=3600
DEFAULT_EXPIRY_DAYS=30
RATE_LIMIT=10/minute
```

---

## app/main.py

```python
from fastapi import FastAPI
from app.routes import shorten, redirect
from app.db.mongo import connect_db, close_db
from app.services.cleanup_service import start_cleanup_scheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="URL Shortener", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(shorten.router)
app.include_router(redirect.router)

@app.on_event("startup")
async def startup():
    await connect_db()
    start_cleanup_scheduler()

@app.on_event("shutdown")
async def shutdown():
    await close_db()

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## app/config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongo_uri: str
    mongo_db_name: str = "urlshortener"
    upstash_redis_url: str
    base_url: str
    cache_ttl_seconds: int = 3600
    default_expiry_days: int = 30
    rate_limit: str = "10/minute"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## .gitignore

```
.env
__pycache__/
*.pyc
.pytest_cache/
venv/
.DS_Store
```

---

## Acceptance Criteria
- [ ] `uvicorn app.main:app --reload` starts without errors
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] All folders and `__init__.py` files exist
- [ ] `.env.example` is committed, `.env` is not
- [ ] No hardcoded secrets anywhere in code
