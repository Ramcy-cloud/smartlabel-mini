"""Cycle de vie d'une session : création à la connexion, expiration, révocation à la déconnexion."""
import time

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
    monkeypatch.delenv("SESSION_TTL_HOURS", raising=False)
    auth._failed_logins.clear()
    auth.clear_sessions()
    yield TestClient(create_app())
    auth._failed_logins.clear()
    auth.clear_sessions()


def connect(client):
    response = client.post("/api/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_each_login_gets_its_own_token(client):
    first, second = connect(client), connect(client)
    assert first != second
    # Les deux sessions sont valables en parallèle
    for token in (first, second):
        assert client.get("/api/label-sets", headers=bearer(token)).status_code == 200


def test_login_announces_how_long_the_session_lasts(client):
    response = client.post("/api/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.json()["expires_in"] == auth.DEFAULT_SESSION_TTL_HOURS * 3600


def test_an_expired_token_no_longer_opens_the_api(client):
    token = connect(client)
    assert client.get("/api/label-sets", headers=bearer(token)).status_code == 200
    # On fait comme si la durée de validité était écoulée
    auth._sessions[token] = time.monotonic() - 1
    assert client.get("/api/label-sets", headers=bearer(token)).status_code == 401
    assert token not in auth._sessions  # la session est oubliée, pas seulement refusée


def test_logout_revokes_the_token_server_side(client):
    token = connect(client)
    assert client.post("/api/logout", headers=bearer(token)).status_code == 204
    # Un jeton intercepté avant la déconnexion ne sert plus à rien
    assert client.get("/api/label-sets", headers=bearer(token)).status_code == 401


def test_logout_only_revokes_the_session_that_asked(client):
    kept, closed = connect(client), connect(client)
    client.post("/api/logout", headers=bearer(closed))
    assert client.get("/api/label-sets", headers=bearer(kept)).status_code == 200


def test_logout_requires_a_valid_token(client):
    assert client.post("/api/logout").status_code == 401
    assert client.post("/api/logout", headers=bearer("faux-jeton")).status_code == 401


def test_the_number_of_sessions_is_capped(client):
    first = connect(client)
    for _ in range(auth.MAX_SESSIONS):
        connect(client)
    assert len(auth._sessions) <= auth.MAX_SESSIONS
    # La session la plus ancienne a été oubliée pour laisser la place
    assert client.get("/api/label-sets", headers=bearer(first)).status_code == 401


def test_a_token_does_not_survive_a_restart(client):
    token = connect(client)
    auth.clear_sessions()  # équivalent d'un redémarrage du backend
    assert client.get("/api/label-sets", headers=bearer(token)).status_code == 401


@pytest.mark.parametrize("value,expected_hours", [
    ("1", 1), ("48", 48), ("0", 1), ("-5", 1), ("10000", 24 * 7), ("abc", auth.DEFAULT_SESSION_TTL_HOURS),
])
def test_session_duration_is_read_and_clamped(monkeypatch, value, expected_hours):
    monkeypatch.setenv("SESSION_TTL_HOURS", value)
    assert auth.session_ttl_seconds() == expected_hours * 3600


def test_tokens_are_long_and_random():
    tokens = {auth.issue_token() for _ in range(20)}
    assert len(tokens) == 20
    assert all(len(t) >= 32 for t in tokens)
    auth.clear_sessions()
