"""Verify MongoDB + Upstash Redis connections using values from .env.

Usage:
    python scripts/check_connections.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.mongo import connect_db, close_db
from app.services.cache_service import ping as redis_ping, get_redis


async def check_mongo() -> tuple[bool, str]:
    try:
        await connect_db()
        return True, f"MongoDB OK (db={settings.mongo_db_name})"
    except Exception as e:
        return False, f"MongoDB FAIL: {e}"
    finally:
        await close_db()


async def check_redis() -> tuple[bool, str]:
    try:
        ok = await redis_ping()
        return bool(ok), "Redis OK" if ok else "Redis FAIL: ping returned falsy"
    except Exception as e:
        return False, f"Redis FAIL: {e}"
    finally:
        try:
            await (await get_redis()).aclose()
        except Exception:
            pass


async def main() -> int:
    print(f"BASE_URL={settings.base_url}")
    results = await asyncio.gather(check_mongo(), check_redis())
    all_ok = True
    for ok, msg in results:
        print(("[OK]  " if ok else "[FAIL]") + " " + msg)
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
