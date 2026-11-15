"""Protections vérifiées ici : taille du corps non annoncée, surface publique de l'API, bornes mémoire."""
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from conftest import auth_headers
from app import auth, security
from app.main import create_app
from app.security import MAX_BODY_BYTES, SecurityMiddleware

BODY = {"tickets": [{"text": "Bonjour"}], "categories": ["a", "b"]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ENABLE_DOCS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
    return TestClient(create_app(), headers=auth_headers())


# --------------------------------------------------------------------- taille du corps
def test_body_sent_in_chunks_is_refused_before_being_read(client):
    """Sans Content-Length, la limite de taille serait contournée : le corps serait lu en entier."""

    def huge_chunks():
        for _ in range(3):
            yield b"x" * (MAX_BODY_BYTES // 2)

    response = client.post(
        "/api/triage", content=huge_chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 411


def test_malformed_content_length_is_refused(client):
    response = client.post(
        "/api/triage", content=b"{}", headers={"Content-Length": "abc", "Content-Type": "application/json"}
    )
    assert response.status_code == 411


def test_announced_oversized_body_is_still_refused(client):
    response = client.post(
        "/api/triage", content=b"x" * (MAX_BODY_BYTES + 1), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


@pytest.mark.parametrize("method,path", [("get", "/api/label-sets"), ("delete", "/api/label-sets/x")])
def test_methods_without_body_are_not_affected(client, method, path):
    assert getattr(client, method)(path).status_code in (200, 404)


def test_a_normal_request_still_passes(client):
    assert client.post("/api/triage", json=BODY).status_code == 200


# --------------------------------------------------------------------- surface publique
@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_interactive_docs_are_closed_by_default(client, path):
    """Le schéma complet de l'API (routes, champs, limites) ne doit pas être lisible sans jeton."""
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("value", ["1", "true", "oui"])
def test_docs_can_be_opened_explicitly(monkeypatch, value):
    monkeypatch.setenv("ENABLE_DOCS", value)
    assert TestClient(create_app()).get("/openapi.json").status_code == 200


def test_testserver_is_not_an_allowed_host_by_default(monkeypatch):
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    assert "testserver" not in security.get_allowed_hosts()
    assert security.get_allowed_hosts() == ["localhost", "127.0.0.1"]


def test_content_security_policy_forbids_every_external_resource(client):
    policy = client.get("/api/label-sets").headers["content-security-policy"]
    assert "default-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy


# --------------------------------------------------------------------- bornes mémoire
def test_idle_clients_are_forgotten_by_the_rate_limiter():
    middleware = SecurityMiddleware(app=None, rate_limit=5)
    for i in range(100):
        middleware._too_many(f"10.0.0.{i}")
    assert len(middleware._hits) == 100
    # Une fenêtre plus tard, les adresses inactives ne sont plus suivies
    middleware._last_sweep -= security.RATE_WINDOW_SECONDS + 1
    for address in middleware._hits.values():
        address[-1] -= security.RATE_WINDOW_SECONDS + 1
    middleware._too_many("10.0.1.1")
    assert len(middleware._hits) == 1


def test_rate_limiter_forgets_the_least_recently_seen_client_at_capacity(monkeypatch):
    """Refuser l'arrivant ferait d'une borne mémoire un déni de service : ce middleware tourne
    avant l'authentification, donc des requêtes sans jeton suffisent à remplir la table."""
    monkeypatch.setattr(security, "MAX_TRACKED_CLIENTS", 3)
    middleware = SecurityMiddleware(app=None, rate_limit=5)
    assert [middleware._too_many(f"10.0.0.{i}") for i in range(3)] == [False, False, False]

    assert middleware._too_many("10.0.0.99") is False  # l'arrivant est servi, pas refusé
    assert len(middleware._hits) == 3  # la table reste bornée
    assert "10.0.0.0" not in middleware._hits  # l'adresse vue le plus anciennement est oubliée
    assert "10.0.0.99" in middleware._hits


def test_rate_limiter_still_refuses_a_client_over_its_quota(monkeypatch):
    """L'éviction ne doit pas ouvrir une porte : la limite par adresse s'applique toujours."""
    monkeypatch.setattr(security, "MAX_TRACKED_CLIENTS", 3)
    middleware = SecurityMiddleware(app=None, rate_limit=2)
    assert [middleware._too_many("10.0.0.1") for _ in range(4)] == [False, False, True, True]


def test_failed_logins_of_idle_clients_are_forgotten():
    auth._failed_logins.clear()
    for i in range(100):
        auth.record_failed_login(f"10.0.0.{i}")
    for times in auth._failed_logins.values():
        times[-1] -= auth.LOGIN_LOCKOUT_SECONDS + 1
    auth.check_login_rate_limit("10.0.1.1")
    assert list(auth._failed_logins) == []


def test_failed_logins_are_evicted_not_ignored_beyond_capacity(monkeypatch):
    """Renoncer à mémoriser priverait toute nouvelle adresse de verrouillage : la seule
    protection contre la force brute céderait justement sous la charge d'une attaque."""
    auth._failed_logins.clear()
    monkeypatch.setattr(auth, "MAX_TRACKED_LOGIN_CLIENTS", 3)
    for i in range(10):
        auth.record_failed_login(f"10.0.0.{i}")
    assert len(auth._failed_logins) == 3  # la table reste bornée
    # Ce sont les adresses vues le plus récemment qui restent suivies
    assert set(auth._failed_logins) == {"10.0.0.7", "10.0.0.8", "10.0.0.9"}
    auth._failed_logins.clear()


def test_a_new_client_is_still_locked_out_when_the_table_is_full(monkeypatch):
    auth._failed_logins.clear()
    monkeypatch.setattr(auth, "MAX_TRACKED_LOGIN_CLIENTS", 3)
    for i in range(3):
        auth.record_failed_login(f"10.0.0.{i}")
    # Une adresse inconnue arrive alors que la table est pleine : ses échecs comptent quand même
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        auth.record_failed_login("10.0.9.9")
    with pytest.raises(HTTPException) as refus:
        auth.check_login_rate_limit("10.0.9.9")
    assert refus.value.status_code == 429
    auth._failed_logins.clear()


def test_trained_model_cache_does_not_grow_without_bound(tmp_path, monkeypatch):
    """Le cache est indexé par (chemin, date, taille) : chaque réentraînement ajoute une entrée.
    Le plafond est abaissé pour que le test échoue si l'éviction disparaît."""
    from app.services import trained_engine

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(trained_engine, "MAX_CACHED_MODELS", 3)
    trained_engine._cache.clear()
    path = tmp_path / "m.json"
    keys = []
    for size in range(1, 9):  # une taille différente à chaque fois, donc une nouvelle clé
        path.write_text('{"version": 0}' + " " * size, encoding="utf-8")
        trained_engine.load_models()
        keys.append((str(path), path.stat().st_mtime_ns, path.stat().st_size))
    assert len(trained_engine._cache) == 3
    assert keys[-1] in trained_engine._cache  # la dernière lecture est mémorisée
    assert keys[0] not in trained_engine._cache  # la plus ancienne est oubliée
    trained_engine._cache.clear()


def test_a_valid_model_survives_an_eviction_of_the_cache(tmp_path, monkeypatch):
    """_load_one lisait le cache hors de son verrou : une éviction concurrente pouvait lui faire
    retourner None, et un modèle valide disparaissait du tri sans trace ni journal."""
    from app.services import trained_engine

    monkeypatch.setattr(trained_engine, "MAX_CACHED_MODELS", 1)
    trained_engine._cache.clear()
    model = {
        "version": trained_engine.MODEL_VERSION,
        "name": "essai",
        "categories": ["a", "b"],
        "coef": [[0.1, 0.2]],
        "intercept": [0.0],
    }
    for name in ("m1.json", "m2.json"):
        (tmp_path / name).write_text(json.dumps(model), encoding="utf-8")
    # Deux fichiers pour un cache d'une seule entrée : chaque chargement évince l'autre
    for _ in range(3):
        assert len(trained_engine.load_models(tmp_path)) == 2
    trained_engine._cache.clear()


# --------------------------------------------------------------------- limites de /predict
@pytest.mark.parametrize("body", [
    {"text": "x" * 5001, "candidate_labels": ["a", "b"]},            # texte au-delà de la limite
    {"text": "", "candidate_labels": ["a", "b"]},                    # texte vide
    {"text": "x", "candidate_labels": [f"l{i}" for i in range(21)]}, # trop de libellés
    {"text": "x", "candidate_labels": ["a"]},                        # un seul libellé
    {"text": "x", "candidate_labels": []},
    {"text": "x", "candidate_labels": ["a", "a"]},                   # doublon
    {"text": "x", "candidate_labels": ["a", "  "]},                  # libellé vide
    {"text": "x", "candidate_labels": ["a", "b" * 101]},             # libellé trop long
])
def test_predict_refuses_work_without_bounds(client, body):
    """Le modèle évalue le texte une fois par libellé : sans limites, un appel suffit à saturer le serveur."""
    assert client.post("/api/predict", json=body).status_code == 422


def test_predict_still_accepts_a_normal_request(client):
    response = client.post("/api/predict", json={"text": "colis en retard", "candidate_labels": ["a", "b"]})
    assert response.status_code == 200
    assert response.json()["predicted_label"] == "a"


def test_predict_is_a_synchronous_route_so_it_never_blocks_the_event_loop():
    """Une route « async » qui appelle le modèle bloquerait tout le serveur pendant l'inférence."""
    import inspect

    from app.api import routes

    assert not inspect.iscoroutinefunction(routes.predict)


def test_predict_and_triage_share_the_inference_lock():
    """Une seule inférence à la fois sur le processeur, quelle que soit la route."""
    from app.api import routes

    assert routes._inference_lock.acquire(blocking=False)
    routes._inference_lock.release()


def test_the_heavy_model_is_not_imported_at_startup():
    """Importer les routes ne doit pas charger le modèle zero-shot (plusieurs Go téléchargés)."""
    import pathlib

    from app.api import routes

    source = pathlib.Path(routes.__file__).read_text(encoding="utf-8")
    header = source.split("router = APIRouter()")[0]
    assert "ai_service" not in header


# --------------------------------------------------------------------- en-têtes sur les refus
# Le corps est construit dans le test et non passé en paramètre : pytest met la valeur dans
# l'identifiant du test, et un corps d'1 Mo dépasse la taille maximale d'une variable
# d'environnement sous Windows (PYTEST_CURRENT_TEST).
@pytest.mark.parametrize("case,expected", [("corps trop gros", 413), ("taille non annoncée", 411)])
def test_refusals_carry_the_security_headers(client, case, expected):
    """Un 411 ou un 413 reste une réponse de l'API : le README annonce ces en-têtes partout."""
    if expected == 413:
        extra_headers, content = {}, b"x" * (MAX_BODY_BYTES + 1)
    else:
        extra_headers, content = {"Content-Length": "abc"}, b"{}"
    response = client.post(
        "/api/triage", headers={"Content-Type": "application/json", **extra_headers}, content=content
    )
    assert response.status_code == expected
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_the_rate_limit_refusal_carries_the_security_headers(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    limited = TestClient(create_app(), headers=auth_headers())
    assert limited.post("/api/triage", json=BODY).status_code == 200
    response = limited.post("/api/triage", json=BODY)
    assert response.status_code == 429
    assert response.headers["retry-after"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in response.headers["content-security-policy"]
