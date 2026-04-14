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
