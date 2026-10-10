import os
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Une requête légitime (50 tickets de 5000 caractères au maximum) reste très en dessous de cette taille
MAX_BODY_BYTES = 1_000_000
RATE_LIMITED_PATHS = ("/api/predict", "/api/triage")
RATE_WINDOW_SECONDS = 60


def get_rate_limit() -> int:
    """Nombre maximal de requêtes d'IA par minute et par adresse IP (RATE_LIMIT_PER_MINUTE)."""
    try:
        return max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
    except ValueError:
        return 60


def get_allowed_hosts() -> list[str]:
    """Noms d'hôte acceptés (ALLOWED_HOSTS, séparés par des virgules) : protège contre les en-têtes Host forgés."""
    raw = os.getenv("ALLOWED_HOSTS", "")
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return hosts or ["localhost", "127.0.0.1", "testserver"]


class SecurityMiddleware(BaseHTTPMiddleware):
    """Limite la taille des requêtes et le débit des routes d'IA, et ajoute des en-têtes de sécurité."""

    def __init__(self, app, rate_limit: int | None = None):
        super().__init__(app)
        self.rate_limit = rate_limit or get_rate_limit()
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _too_many(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] > RATE_WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= self.rate_limit:
                return True
            hits.append(now)
            return False

    async def dispatch(self, request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Requête trop volumineuse."}, status_code=413)

        if request.method == "POST" and request.url.path in RATE_LIMITED_PATHS:
            client = request.client.host if request.client else "inconnu"
            if self._too_many(client):
                return JSONResponse(
                    {"detail": "Trop de requêtes, réessayez dans une minute."},
                    status_code=429,
                    headers={"Retry-After": str(RATE_WINDOW_SECONDS)},
                )

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response
