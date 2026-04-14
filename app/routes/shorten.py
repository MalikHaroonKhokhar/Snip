from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.models.url_model import ShortenRequest, ShortenResponse
from app.services.url_service import create_short_url

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/shorten", response_model=ShortenResponse)
@limiter.limit(settings.rate_limit)
async def shorten_url(request: Request, body: ShortenRequest) -> ShortenResponse:
    return await create_short_url(body)
