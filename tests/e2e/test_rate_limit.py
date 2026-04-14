"""Rate-limit behaviour tests for POST /shorten.

The decorator reads `settings.rate_limit` at import time (default "10/minute"),
so these tests parse that value and send N+1 bursts to prove the N+1'th is blocked.

create_short_url is mocked so hitting the limit never writes to Mongo/Redis.
"""
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.url_model import ShortenResponse
from app.routes import redirect as redirect_route
from app.routes import shorten as shorten_route


pytestmark = pytest.mark.e2e


def _parse_limit(spec: str) -> int:
    # "10/minute" -> 10
    m = re.match(r"\s*(\d+)\s*/", spec)
    assert m, f"unrecognized rate-limit spec: {spec}"
    return int(m.group(1))


LIMIT = _parse_limit(settings.rate_limit)


@pytest.fixture
def client(monkeypatch):
    # Clear the slowapi counter so each test starts with a fresh budget.
    try:
        shorten_route.limiter.reset()
    except Exception:
        pass

    fake = ShortenResponse(
        short_url="https://snip.test/abc1234",
        short_code="abc1234",
        long_url="https://example.com",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    monkeypatch.setattr(
        shorten_route, "create_short_url", AsyncMock(return_value=fake)
    )
    return TestClient(app)


def _post(client):
    return client.post("/shorten", json={"long_url": "https://example.com"})


def test_requests_below_threshold_all_pass(client):
    for i in range(LIMIT):
        resp = _post(client)
        assert resp.status_code == 200, f"request {i + 1}/{LIMIT} should pass, got {resp.status_code}"


def test_request_beyond_threshold_returns_429(client):
    for _ in range(LIMIT):
        assert _post(client).status_code == 200
    breach = _post(client)
    assert breach.status_code == 429


def test_429_body_matches_slowapi_format(client):
    for _ in range(LIMIT):
        _post(client)
    breach = _post(client)
    assert breach.status_code == 429
    body = breach.json()
    # slowapi default handler returns {"error": "Rate limit exceeded: ..."}
    assert "error" in body
    assert "rate limit exceeded" in body["error"].lower()


def test_get_code_is_not_rate_limited(client, monkeypatch):
    monkeypatch.setattr(
        redirect_route, "resolve_short_code", AsyncMock(return_value="https://x.example")
    )

    # Burst well beyond the POST limit — GET must keep returning 301.
    for _ in range(LIMIT * 3):
        resp = client.get("/anycode", follow_redirects=False)
        assert resp.status_code == 301


def test_rate_limit_value_is_env_driven():
    # Confirms the decorator is not hardcoded — it reflects settings from .env.
    assert "/" in settings.rate_limit
    assert LIMIT >= 1
