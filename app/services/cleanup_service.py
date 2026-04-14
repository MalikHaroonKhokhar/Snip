import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.mongo import get_db
from app.services.cache_service import delete_from_cache

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_MINUTES = 5
LOOKBACK_MINUTES = 10

scheduler: AsyncIOScheduler | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def cleanup_expired_urls() -> int:
    """Invalidate Redis entries for recently-expired URLs and soft-delete them.

    Returns the number of entries processed (handy for tests + logs).
    """
    db = get_db()
    if db is None:
        logger.warning("cleanup skipped: db not initialised")
        return 0

    now = _utcnow()
    window_start = now - timedelta(minutes=LOOKBACK_MINUTES)

    cursor = db.urls.find(
        {
            "expires_at": {"$gte": window_start, "$lte": now},
            "is_active": True,
        }
    )

    count = 0
    async for doc in cursor:
        short_code = doc["short_code"]
        await delete_from_cache(short_code)
        await db.urls.update_one(
            {"short_code": short_code}, {"$set": {"is_active": False}}
        )
        count += 1

    if count:
        logger.info("cleanup invalidated %d expired URL(s)", count)
    return count


def start_cleanup_scheduler(interval_minutes: int = CLEANUP_INTERVAL_MINUTES) -> None:
    global scheduler
    if scheduler is None or not scheduler.running:
        scheduler = AsyncIOScheduler()
    scheduler.add_job(
        cleanup_expired_urls,
        trigger="interval",
        minutes=interval_minutes,
        id="url_cleanup",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("cleanup scheduler started (every %d min)", interval_minutes)


def stop_cleanup_scheduler() -> None:
    global scheduler
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("cleanup scheduler stopped")
    scheduler = None
