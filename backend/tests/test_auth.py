import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import create_app

EMAIL = "equipe@example.com"
PASSWORD = "mot-de-passe-éàü-solide"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, "APP_EMAIL", EMAIL)
    monkeypatch.setattr(auth, "APP_PASSWORD", PASSWORD)
    auth._failed_logins.clear()
    yield TestClient(create_app())
    auth._failed_logins.clear()


def login(client, email, password):
    return client.post("/api/login", json={"email": email, "password": password})


PROTECTED = [
    ("post", "/api/predict", {"text": "x", "candidate_labels": ["a", "b"]}),
    ("post", "/api/triage", {"tickets": [{"text": "x"}], "categories": ["a", "b"]}),
    ("get", "/api/label-sets", None),
    ("put", "/api/label-sets/x", {"categories": ["a", "b"]}),
    ("delete", "/api/label-sets/x", None),
]


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_routes_require_a_token(client, method, path, body):
    assert getattr(client, method)(path, **({"json": body} if body else {})).status_code == 401


@pytest.mark.parametrize("header", ["Bearer faux-jeton", "Basic abc", "Bearer ", ""])
def test_invalid_authorization_headers_are_refused(client, header):
    assert client.get("/api/label-sets", headers={"Authorization": header}).status_code == 401


def test_login_gives_a_token_that_opens_the_api(client):
    res = login(client, EMAIL, PASSWORD)
    assert res.status_code == 200
    token = res.json()["token"]
    ok = client.get("/api/label-sets", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200


def test_email_is_case_insensitive_but_password_is_not(client):
    assert login(client, EMAIL.upper(), PASSWORD).status_code == 200
    assert login(client, EMAIL, PASSWORD.upper()).status_code == 401


@pytest.mark.parametrize("email,password", [
    ("", PASSWORD), (EMAIL, ""), ("", ""), (EMAIL, "mauvais"), ("autre@example.com", PASSWORD),
    ("é" * 10, "ü" * 10),  # texte non ASCII : refus propre, pas d'erreur serveur
])
def test_bad_credentials_are_refused(client, email, password):
    assert login(client, email, password).status_code == 401


@pytest.mark.parametrize("email,password", [("", ""), (EMAIL, ""), ("", PASSWORD)])
def test_login_is_refused_when_not_configured(monkeypatch, email, password):
    monkeypatch.setattr(auth, "APP_EMAIL", email)
    monkeypatch.setattr(auth, "APP_PASSWORD", password)
    res = login(TestClient(create_app()), EMAIL, PASSWORD)
    assert res.status_code == 503


def test_lockout_after_repeated_failures(client):
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        assert login(client, EMAIL, "mauvais").status_code == 401
    # Même le bon mot de passe est refusé pendant le verrouillage
    res = login(client, EMAIL, PASSWORD)
    assert res.status_code == 429
    assert "retry-after" in res.headers


def test_login_input_sizes_are_limited(client):
    assert login(client, "a" * 300, "x").status_code == 422
    assert login(client, "a@b.c", "x" * 300).status_code == 422


def test_cors_preflight_allows_authorization_header(client):
    ok = client.options("/api/triage", headers={
        "Origin": "http://localhost:5175",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert ok.status_code == 200
