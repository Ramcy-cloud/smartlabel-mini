import logging
import os
import secrets
import time
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

# Charge backend/.env s'il existe (APP_EMAIL / APP_PASSWORD)
load_dotenv()

APP_EMAIL = os.getenv("APP_EMAIL", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

# Jeton de session régénéré à chaque démarrage du backend : un redémarrage force une reconnexion.
SESSION_TOKEN = secrets.token_hex(32)

# Anti brute-force : verrouillage temporaire par IP après plusieurs échecs (mémoire, un seul processus)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60
_failed_logins: dict[str, list[float]] = defaultdict(list)

router = APIRouter()


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


def check_login_rate_limit(client_id: str) -> None:
    now = time.time()
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


def record_failed_login(client_id: str) -> None:
    _failed_logins[client_id].append(time.time())


def reset_login_attempts(client_id: str) -> None:
    _failed_logins.pop(client_id, None)


def get_current_token(authorization: str | None = Header(default=None)) -> str:
    """Dépendance FastAPI : vérifie l'en-tête « Authorization: Bearer <jeton> »."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise.")
    token = authorization.removeprefix("Bearer ").strip()
    if not _same(token, SESSION_TOKEN):
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
    return {"token": SESSION_TOKEN}
