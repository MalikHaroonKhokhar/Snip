from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl


class ShortenRequest(BaseModel):
    long_url: HttpUrl
    custom_code: Optional[str] = None
    expiry_days: Optional[int] = None


class ShortenResponse(BaseModel):
    short_url: str
    short_code: str
    long_url: str
    expires_at: datetime


class URLDocument(BaseModel):
    short_code: str
    long_url: str
    created_at: datetime
    expires_at: datetime
    hits: int = 0
    is_active: bool = True
