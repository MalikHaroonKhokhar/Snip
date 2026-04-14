from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.url_model import ShortenRequest, ShortenResponse, URLDocument


pytestmark = pytest.mark.unit


def test_shorten_request_accepts_valid_url():
    req = ShortenRequest(long_url="https://example.com/path?x=1")
    assert str(req.long_url).startswith("https://example.com")
    assert req.custom_code is None
    assert req.expiry_days is None


def test_shorten_request_rejects_invalid_url():
    with pytest.raises(ValidationError):
        ShortenRequest(long_url="not-a-url")


def test_shorten_request_optional_fields():
    req = ShortenRequest(
        long_url="https://a.co", custom_code="abc123", expiry_days=7
    )
    assert req.custom_code == "abc123"
    assert req.expiry_days == 7


def test_url_document_defaults():
    now = datetime.now(timezone.utc)
    doc = URLDocument(
        short_code="aB3xY9z",
        long_url="https://example.com",
        created_at=now,
        expires_at=now + timedelta(days=30),
    )
    assert doc.hits == 0
    assert doc.is_active is True


def test_shorten_response_requires_all_fields():
    with pytest.raises(ValidationError):
        ShortenResponse(short_url="x", short_code="y", long_url="z")  # missing expires_at
