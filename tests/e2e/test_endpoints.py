from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.url_model import ShortenResponse
from app.routes import redirect as redirect_route
from app.routes import shorten as shorten_route


pytestmark = pytest.mark.e2e


@pytest.fixture
def client():
    # Bare TestClient (no `with`) so the real lifespan/DB connect does not run —
    # endpoint behavior is exercised against mocked service dependencies.
    return TestClient(app)


def test_shorten_returns_200_with_valid_url(client, monkeypatch):
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    fake_response = ShortenResponse(
        short_url="https://snip.test/abc1234",
        short_code="abc1234",
        long_url="https://example.com/hello",
        expires_at=expires,
    )
    monkeypatch.setattr(
        shorten_route, "create_short_url", AsyncMock(return_value=fake_response)
    )

    resp = client.post("/shorten", json={"long_url": "https://example.com/hello"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["short_code"] == "abc1234"
    assert body["short_url"].endswith("/abc1234")
    assert body["long_url"] == "https://example.com/hello"


def test_shorten_rejects_invalid_url_with_422(client):
    resp = client.post("/shorten", json={"long_url": "not-a-url"})
    assert resp.status_code == 422


def test_redirect_returns_301_on_hit(client, monkeypatch):
    monkeypatch.setattr(
        redirect_route,
        "resolve_short_code",
        AsyncMock(return_value="https://example.com/target"),
    )

    resp = client.get("/abc1234", follow_redirects=False)

    assert resp.status_code == 301
    assert resp.headers["location"] == "https://example.com/target"


def test_redirect_returns_404_when_unknown(client, monkeypatch):
    monkeypatch.setattr(
        redirect_route, "resolve_short_code", AsyncMock(return_value=None)
    )

    resp = client.get("/missing", follow_redirects=False)

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_redirect_returns_404_on_expired(client, monkeypatch):
    # resolve_short_code returns None for expired codes (see unit tests)
    monkeypatch.setattr(
        redirect_route, "resolve_short_code", AsyncMock(return_value=None)
    )

    resp = client.get("/expired", follow_redirects=False)

    assert resp.status_code == 404
