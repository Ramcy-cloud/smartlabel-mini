import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app import auth
from app.api.routes import router
from app.security import SecurityMiddleware, get_allowed_hosts

# Origines du frontend local (Docker : 5175, Vite en dev : 5173) utilisées si ALLOWED_ORIGINS est absente
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5175", "http://localhost:5173"]


def get_allowed_origins() -> list[str]:
    """Lit ALLOWED_ORIGINS (origines séparées par des virgules, espaces ignorés)."""
    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if "*" in origins:
        raise ValueError("ALLOWED_ORIGINS ne doit pas contenir '*' : listez les origines explicitement.")
    return origins or list(DEFAULT_ALLOWED_ORIGINS)


def create_app() -> FastAPI:
    auth.warn_if_unconfigured()
    app = FastAPI(title="SmartLabel-Mini API", description="API IA pour la labellisation de données")

    # Les middlewares s'empilent : le dernier ajouté est le plus extérieur.
    # SecurityMiddleware est à l'intérieur de CORS pour que ses refus (413, 429) portent aussi les en-têtes CORS.
    app.add_middleware(SecurityMiddleware)

    # L'authentification passe par l'en-tête Authorization (pas de cookies) : pas de credentials.
    # Seules les origines listées, les méthodes et en-têtes réellement utilisés par le frontend sont autorisés.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_allowed_hosts())

    # /api/login est public ; toutes les autres routes exigent un jeton valide
    app.include_router(auth.router, prefix="/api")
    app.include_router(router, prefix="/api", dependencies=[Depends(auth.get_current_token)])
    return app


app = create_app()
