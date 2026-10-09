import pytest
from fastapi.testclient import TestClient

from app.main import DEFAULT_ALLOWED_ORIGINS, create_app

ALLOWED = "http://localhost:5175"
MALICIOUS = "https://site-malveillant.example"


def preflight(client, origin):
    return client.options(
        "/api/predict",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    return TestClient(create_app())


def test_preflight_from_allowed_origin(client):
    response = preflight(client, ALLOWED)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_from_unknown_origin_has_no_cors_header(client):
    response = preflight(client, MALICIOUS)
    assert "access-control-allow-origin" not in response.headers


def test_actual_request_from_unknown_origin_has_no_cors_header(client):
    response = client.post(
        "/api/predict",
        json={"text": "bonjour", "candidate_labels": ["a", "b"]},
        headers={"Origin": MALICIOUS},
    )
    assert "access-control-allow-origin" not in response.headers


def test_actual_request_from_allowed_origin_still_works(client):
    response = client.post(
        "/api/predict",
        json={"text": "bonjour", "candidate_labels": ["a", "b"]},
        headers={"Origin": ALLOWED},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_disallowed_method_and_header_are_rejected(client):
    response = client.options(
        "/api/predict",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "x-custom",
        },
    )
    assert response.status_code == 400


def test_default_origins_are_local_frontend_only(client):
    assert "*" not in DEFAULT_ALLOWED_ORIGINS
    assert all(o.startswith("http://localhost:") for o in DEFAULT_ALLOWED_ORIGINS)


def test_multiple_origins_from_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://a.example , https://b.example ,,")
    client = TestClient(create_app())
    for origin in ("https://a.example", "https://b.example"):
        assert preflight(client, origin).headers["access-control-allow-origin"] == origin
    # La valeur par défaut ne s'applique plus quand la variable est définie
    assert "access-control-allow-origin" not in preflight(client, ALLOWED).headers
    assert "access-control-allow-origin" not in preflight(client, MALICIOUS).headers


def test_wildcard_in_env_is_refused(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(ValueError):
        create_app()
