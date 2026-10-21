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
# Méthodes qui portent un corps : leur taille doit être annonçable et vérifiable avant lecture
BODY_METHODS = ("POST", "PUT", "PATCH")
# Nombre d'adresses suivies par le compteur de débit : borne la mémoire face à un trafic de milliers d'IP
MAX_TRACKED_CLIENTS = 10_000
# Les pages de documentation chargent leurs scripts depuis un CDN : la politique stricte ne s'y applique pas
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
# Une réponse d'API est du JSON : elle n'a besoin d'aucune ressource externe et ne doit jamais être encadrée
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


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
    return hosts or ["localhost", "127.0.0.1"]


class SecurityMiddleware(BaseHTTPMiddleware):
    """Limite la taille des requêtes et le débit des routes d'IA, et ajoute des en-têtes de sécurité."""

    def __init__(self, app, rate_limit: int | None = None):
        super().__init__(app)
        self.rate_limit = rate_limit or get_rate_limit()
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _forget_idle_clients(self, now: float) -> None:
        """Oublie les adresses sans requête récente : sans cela le dictionnaire grossit à chaque nouvelle IP."""
        if now - self._last_sweep < RATE_WINDOW_SECONDS:
            return
        self._last_sweep = now
        for address in [a for a, hits in self._hits.items() if not hits or now - hits[-1] > RATE_WINDOW_SECONDS]:
            del self._hits[address]

    def _too_many(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._forget_idle_clients(now)
            if client not in self._hits and len(self._hits) >= MAX_TRACKED_CLIENTS:
                return True  # trop d'adresses suivies : on refuse plutôt que de laisser la mémoire croître
            hits = self._hits[client]
            while hits and now - hits[0] > RATE_WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= self.rate_limit:
                return True
            hits.append(now)
            return False

    @staticmethod
    def _body_refusal(request) -> JSONResponse | None:
        """Refuse un corps trop gros, ou dont la taille n'est pas annoncée.

        Un corps envoyé « en morceaux » (Transfer-Encoding: chunked) n'annonce pas sa taille : il serait
        lu en entier avant toute vérification, et la limite ne servirait à rien. On exige donc un
        Content-Length exploitable sur les méthodes qui portent un corps.
        """
        if request.method not in BODY_METHODS:
            return None
        length = request.headers.get("content-length")
        if length is None or not length.isdigit():
            return JSONResponse(
                {"detail": "La taille du corps de la requête doit être annoncée (Content-Length)."},
                status_code=411,
            )
        if int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Requête trop volumineuse."}, status_code=413)
        return None

    async def dispatch(self, request, call_next):
        refusal = self._body_refusal(request)
        if refusal is not None:
            return refusal

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
        if not request.url.path.startswith(DOCS_PATHS):
            response.headers["Content-Security-Policy"] = API_CSP
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response
