import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers
from app.main import create_app
from app.security import MAX_BODY_BYTES

BODY = {"tickets": [{"text": "Bonjour"}], "categories": ["a", "b"]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
    return TestClient(create_app(), headers=auth_headers())


def test_security_headers_are_set(client):
    response = client.get("/api/label-sets")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_oversized_body_is_refused_with_cors_headers(client):
    response = client.post(
        "/api/triage",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json", "Origin": "http://localhost:5175"},
    )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5175"


def test_rate_limit_on_ai_routes(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    client = TestClient(create_app(), headers=auth_headers())
    codes = [client.post("/api/triage", json=BODY).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    # Les routes qui ne font pas d'inférence ne sont pas limitées
    assert client.get("/api/label-sets").status_code == 200


def test_unknown_host_is_refused(client):
    response = client.get("/api/label-sets", headers={"Host": "evil.example"})
    assert response.status_code == 400
