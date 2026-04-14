from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.routes import shorten, redirect
from app.db.mongo import connect_db, close_db
from app.services.cleanup_service import start_cleanup_scheduler, stop_cleanup_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    start_cleanup_scheduler()
    yield
    stop_cleanup_scheduler()
    await close_db()


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="URL Shortener", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


INDEX_HTML = Path(__file__).parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(INDEX_HTML)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Prevent /{code} from trying to resolve "favicon.ico" as a short code.
    return Response(status_code=204)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(shorten.router)
app.include_router(redirect.router)
