import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers
from app.main import create_app
from app.services.label_sets import label_set_store
from app.services.priority import compute_priority, default_index, normalize

P3 = ["urgente", "normale", "basse"]


def prio(text, priorities=P3, **kwargs):
    return compute_priority(text, priorities, **kwargs)[0]


@pytest.mark.parametrize("text", [
    "Mon compte est bloqué, c'est URGENT",
    "Plus rien ne fonctionne depuis ce matin",
    "L'application ne marche plus",
    "Nous perdons des ventes à cause du site",
    "J'ai été prélevé deux fois ce mois-ci",
    "Je vais contacter mon avocat",
    "Il y a eu un piratage de mon compte",
    "Envoyez une réponse dans les plus brefs délais",
    "The site is down and customers are blocked",
    "Cela fait depuis trois semaines que j'attends",
])
def test_urgent_signals(text):
    assert prio(text) == "urgente"


@pytest.mark.parametrize("text", [
    "Ce n'est pas urgent, juste pour information",
    "Une simple question sur vos horaires",
    "Une suggestion pour améliorer la page d'accueil",
    "Sans urgence, mais pourriez-vous m'aider ?",
    "Mon compte n'est pas bloqué, merci",
])
def test_low_signals_and_negations(text):
    assert prio(text) == "basse"


def test_no_signal_gives_the_middle_priority():
    assert prio("Bonjour, je voudrais modifier mon adresse") == "normale"


def test_urgent_wins_over_low():
    assert prio("Pour information : mon site est bloqué") == "urgente"


def test_accents_and_case_do_not_matter():
    assert normalize("  BLOQUÉ !! ") == "bloque"
    assert prio("BLOQUÉ") == prio("bloque") == "urgente"


def test_default_index():
    assert [default_index(n) for n in (2, 3, 4, 5)] == [1, 1, 1, 2]
    assert prio("Bonjour", ["haute", "basse"]) == "basse"


def test_vip_and_age_raise_one_step_each():
    assert prio("Bonjour", vip=True) == "urgente"
    assert prio("Bonjour", age_days=7) == "urgente"
    assert prio("Bonjour", age_days=6) == "normale"
    assert prio("Pour information", vip=True) == "normale"
    assert prio("Pour information", vip=True, age_days=30) == "urgente"


def test_category_floor_is_a_minimum():
    floors = {"réclamation": "normale"}
    assert prio("Pour information", category="réclamation", floors=floors) == "normale"
    assert prio("Pour information", category="autre", floors=floors) == "basse"
    # Le plancher ne baisse jamais une priorité déjà plus élevée
    assert prio("C'est bloqué", category="réclamation", floors=floors) == "urgente"


def test_custom_keywords_extend_the_defaults():
    assert prio("La caisse Alpha tombe en erreur") == "normale"
    assert prio("La caisse Alpha tombe en erreur", extra_keywords=["caisse alpha"]) == "urgente"
    assert prio("Mes fuites d'eau", extra_keywords=["fuite"]) == "urgente"
    # Un mot-clé personnalisé nié ne déclenche rien
    assert prio("Pas de fuite", extra_keywords=["fuite"]) != "urgente"


def test_reasons_explain_the_decision():
    _, reasons = compute_priority("Compte bloqué", P3, vip=True, age_days=10)
    assert reasons[0].startswith("mot-clé d'urgence")
    assert any("VIP" in r for r in reasons) and any("10 jours" in r for r in reasons)


def test_text_is_never_executed_as_a_pattern():
    # Les mots-clés personnalisés sont échappés : pas d'expression régulière injectable
    assert prio("Bonjour", extra_keywords=["(a+)+$", ".*"]) == "normale"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(label_set_store, "path", tmp_path / "label_sets.json")
    return TestClient(create_app(), headers=auth_headers())


def test_triage_uses_rules_for_priority(client):
    res = client.post("/api/triage", json={
        "tickets": [{"id": "1", "text": "Mon site est bloqué"}, {"id": "2", "text": "Bonjour", "vip": True},
                    {"id": "3", "text": "Pour information", "age_days": 2}],
        "categories": ["facturation", "autre"],
        "priorities": P3,
    })
    assert res.status_code == 200
    got = {r["id"]: r for r in res.json()["results"]}
    assert got["1"]["priority"] == "urgente" and got["1"]["priority_reasons"]
    assert got["2"]["priority"] == "urgente"
    assert got["3"]["priority"] == "basse"
    assert "priority_confidence" not in got["1"]


def test_triage_floor_uses_the_category_found(client):
    # Le faux modèle des tests choisit la première catégorie : « réclamation »
    res = client.post("/api/triage", json={
        "tickets": [{"text": "Pour information"}],
        "categories": ["réclamation", "autre"], "priorities": P3,
        "floors": {"réclamation": "normale"},
    })
    assert res.json()["results"][0]["priority"] == "normale"


@pytest.mark.parametrize("payload", [
    {"floors": {"inconnue": "normale"}},
    {"floors": {"autre": "inexistante"}},
    {"urgent_keywords": ["x" * 61]},
    {"urgent_keywords": ["a"] * 51},
])
def test_triage_rejects_invalid_rules(client, payload):
    body = {"tickets": [{"text": "x"}], "categories": ["autre", "b"], "priorities": P3, **payload}
    assert client.post("/api/triage", json=body).status_code == 422


@pytest.mark.parametrize("ticket", [{"text": "x", "age_days": -1}, {"text": "x", "age_days": 99999}, {"text": "x", "vip": "peut-être"}])
def test_triage_rejects_invalid_ticket_metadata(client, ticket):
    body = {"tickets": [ticket], "categories": ["a", "b"], "priorities": P3}
    assert client.post("/api/triage", json=body).status_code == 422


def test_label_set_keeps_keywords_and_floors(client):
    body = {"categories": ["rh", "it"], "priorities": ["haute", "basse"],
            "urgent_keywords": ["  serveur  ", "Serveur", ""], "floors": {"it": "haute"}}
    saved = client.put("/api/label-sets/IT", json=body).json()
    assert saved["urgent_keywords"] == ["serveur"]
    assert client.get("/api/label-sets").json()["IT"]["floors"] == {"it": "haute"}
    bad = {**body, "floors": {"it": "moyenne"}}
    assert client.put("/api/label-sets/IT2", json=bad).status_code == 422
