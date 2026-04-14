from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.db.mongo import get_db
from app.models.url_model import ShortenRequest, ShortenResponse
from app.services.cache_service import get_from_cache, set_in_cache
from app.utils.encoder import generate_short_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ShortCodeGenerationError(RuntimeError):
    pass


async def create_short_url(body: ShortenRequest) -> ShortenResponse:
    db = get_db()
    long_url = str(body.long_url)
    expiry_days = body.expiry_days or settings.default_expiry_days
    now = _utcnow()
    expires_at = now + timedelta(days=expiry_days)

    short_code: str | None = None
    for attempt in range(3):
        candidate = generate_short_code()
        doc = {
            "short_code": candidate,
            "long_url": long_url,
            "created_at": now,
            "expires_at": expires_at,
            "hits": 0,
            "is_active": True,
        }
        try:
            await db.urls.insert_one(doc)
            short_code = candidate
            break
        except DuplicateKeyError:
            if attempt == 2:
                raise ShortCodeGenerationError(
                    "Failed to generate unique short code after 3 attempts"
                )
            continue

    assert short_code is not None
    await set_in_cache(short_code, long_url, ttl=settings.cache_ttl_seconds)

    return ShortenResponse(
        short_url=f"{settings.base_url}/{short_code}",
        short_code=short_code,
        long_url=long_url,
        expires_at=expires_at,
    )


async def resolve_short_code(code: str) -> str | None:
    cached = await get_from_cache(code)
    if cached:
        return cached

    db = get_db()
    doc = await db.urls.find_one({"short_code": code, "is_active": True})
    if not doc:
        return None

    if doc["expires_at"] < _utcnow():
        return None

    await set_in_cache(code, doc["long_url"], ttl=settings.cache_ttl_seconds)
    await db.urls.update_one({"short_code": code}, {"$inc": {"hits": 1}})

    return doc["long_url"]
