import logging
import os
import secrets
import threading
import time
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

# Charge backend/.env s'il existe (APP_EMAIL / APP_PASSWORD)
load_dotenv()

APP_EMAIL = os.getenv("APP_EMAIL", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

# Anti brute-force : verrouillage temporaire par IP après plusieurs échecs (mémoire, un seul processus)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60
MAX_TRACKED_LOGIN_CLIENTS = 10_000  # borne la mémoire face à des tentatives venues de milliers d'adresses
_failed_logins: dict[str, list[float]] = defaultdict(list)
_logins_lock = threading.Lock()  # la route de connexion tourne dans un pool de threads

# Sessions : un jeton par connexion, oublié à l'expiration, à la déconnexion et au redémarrage du backend.
DEFAULT_SESSION_TTL_HOURS = 12
MAX_SESSIONS = 50  # au-delà, la session la plus ancienne est oubliée
_sessions: dict[str, float] = {}  # jeton -> instant d'expiration (horloge monotone)
_sessions_lock = threading.Lock()

router = APIRouter()


def session_ttl_seconds() -> int:
    """Durée de validité d'une session, en secondes (SESSION_TTL_HOURS, entre 1 h et 7 jours)."""
    try:
        hours = int(os.getenv("SESSION_TTL_HOURS", str(DEFAULT_SESSION_TTL_HOURS)))
    except ValueError:
        hours = DEFAULT_SESSION_TTL_HOURS
    return min(max(hours, 1), 24 * 7) * 3600


def is_configured() -> bool:
    """Vrai seulement si APP_EMAIL et APP_PASSWORD sont tous deux renseignés."""
    return bool(APP_EMAIL) and bool(APP_PASSWORD)


def warn_if_unconfigured() -> None:
    if not is_configured():
        logging.getLogger("uvicorn.error").warning(
            "APP_EMAIL et/ou APP_PASSWORD non définis : l'authentification n'est pas configurée, "
            "toute connexion sera refusée."
        )


def _same(a: str, b: str) -> bool:
    # Comparaison à temps constant sur des octets : compare_digest lève une erreur sur du texte non ASCII
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_credentials(email: str, password: str) -> bool:
    """Refuse tout si l'authentification n'est pas configurée ou si un champ est vide."""
    if not is_configured() or not email or not password:
        return False
    # Les deux comparaisons sont toujours faites (pas de court-circuit qui révélerait l'email valide)
    email_ok = _same(email.strip().casefold(), APP_EMAIL.strip().casefold())
    password_ok = _same(password, APP_PASSWORD)
    return email_ok and password_ok


# ----------------------------------------------------------------------------- sessions
def _drop_expired(now: float) -> None:
    for token in [t for t, expiry in _sessions.items() if expiry <= now]:
        del _sessions[token]


def issue_token() -> str:
    """Crée une session et retourne son jeton (256 bits aléatoires, jamais dérivé du mot de passe)."""
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _sessions_lock:
        _drop_expired(now)
        while len(_sessions) >= MAX_SESSIONS:
            del _sessions[min(_sessions, key=_sessions.__getitem__)]
        _sessions[token] = now + session_ttl_seconds()
    return token


def is_valid_token(token: str) -> bool:
    now = time.monotonic()
    with _sessions_lock:
        _drop_expired(now)
        # Comparaison à temps constant avec chaque session vivante : un jeton proche n'est pas plus lent
        return any(_same(token, live) for live in _sessions)


def revoke_token(token: str) -> None:
    with _sessions_lock:
        for live in [t for t in _sessions if _same(token, t)]:
            del _sessions[live]


def clear_sessions() -> None:
    """Oublie toutes les sessions (utilisé par les tests)."""
    with _sessions_lock:
        _sessions.clear()


# ----------------------------------------------------------------------------- connexion
def _forget_idle_login_clients(now: float) -> None:
    for client in [c for c, times in _failed_logins.items() if not times or now - times[-1] >= LOGIN_LOCKOUT_SECONDS]:
        del _failed_logins[client]


def check_login_rate_limit(client_id: str) -> None:
    now = time.time()
    with _logins_lock:
        _forget_idle_login_clients(now)
        recent = [t for t in _failed_logins[client_id] if now - t < LOGIN_LOCKOUT_SECONDS]
        if recent:
            _failed_logins[client_id] = recent
        else:
            _failed_logins.pop(client_id, None)
    if len(recent) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives, réessayez dans une minute.",
            headers={"Retry-After": str(LOGIN_LOCKOUT_SECONDS)},
        )


def _forget_least_recent_login_client() -> None:
    """Oublie l'adresse vue le plus anciennement, les entrées vides d'abord."""
    oldest = min(_failed_logins, key=lambda c: _failed_logins[c][-1] if _failed_logins[c] else 0.0)
    del _failed_logins[oldest]


def record_failed_login(client_id: str) -> None:
    with _logins_lock:
        # À saturation on évince, on ne renonce pas à mémoriser : sans trace de ses échecs, une
        # nouvelle adresse ne serait plus jamais verrouillée, et la seule protection contre la
        # force brute sur le mot de passe partagé céderait précisément sous la charge d'une attaque.
        if client_id not in _failed_logins and len(_failed_logins) >= MAX_TRACKED_LOGIN_CLIENTS:
            _forget_least_recent_login_client()
        _failed_logins[client_id].append(time.time())


def reset_login_attempts(client_id: str) -> None:
    with _logins_lock:
        _failed_logins.pop(client_id, None)


def get_current_token(authorization: str | None = Header(default=None)) -> str:
    """Dépendance FastAPI : vérifie l'en-tête « Authorization: Bearer <jeton> »."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise.")
    token = authorization.removeprefix("Bearer ").strip()
    if not is_valid_token(token):
        raise HTTPException(status_code=401, detail="Session invalide ou expirée.")
    return token


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


@router.post("/login")
def login(request: LoginRequest, http_request: Request):
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Authentification non configurée : définissez APP_EMAIL et APP_PASSWORD.",
        )
    client_id = http_request.client.host if http_request.client else "inconnu"
    check_login_rate_limit(client_id)
    if not verify_credentials(request.email, request.password):
        record_failed_login(client_id)
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
    reset_login_attempts(client_id)
    return {"token": issue_token(), "expires_in": session_ttl_seconds()}


@router.post("/logout", status_code=204)
def logout(token: str = Depends(get_current_token)):
    """Oublie la session côté serveur : le jeton devient inutilisable, même s'il a été intercepté."""
    revoke_token(token)
    return Response(status_code=204)
