import pytest
from fastapi.testclient import TestClient

from app.main import app


pytestmark = pytest.mark.e2e


def test_health_endpoint_runs_startup_and_returns_ok():
    # TestClient context manager triggers the real startup event,
    # which connects to MongoDB Atlas and creates indexes.
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
