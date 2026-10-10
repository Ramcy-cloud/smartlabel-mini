import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers
from app.main import create_app
from app.services.label_sets import label_set_store


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(label_set_store, "path", tmp_path / "label_sets.json")
    return TestClient(create_app(), headers=auth_headers())


def test_triage_returns_category_and_priority(client):
    response = client.post("/api/triage", json={
        "tickets": [{"id": "1", "text": "Ma facture est fausse"}, {"text": "Colis perdu"}],
        "categories": ["facturation", "livraison"],
        "priorities": ["urgente", "normale"],
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["id"] for r in results] == ["1", None]
    assert results[0]["category"] == "facturation"
    assert results[0]["priority"] == "urgente"
    assert 0 <= results[0]["category_confidence"] <= 1


def test_triage_without_priorities(client):
    response = client.post("/api/triage", json={
        "tickets": [{"text": "Bonjour"}], "categories": ["a", "b"],
    })
    assert response.status_code == 200
    assert response.json()["results"][0]["priority"] is None


@pytest.mark.parametrize("payload", [
    {"tickets": [], "categories": ["a", "b"]},
    {"tickets": [{"text": "x"}], "categories": ["a"]},
    {"tickets": [{"text": "x"}], "categories": ["a", " A "]},
    {"tickets": [{"text": "x"}], "categories": ["a", ""]},
    {"tickets": [{"text": ""}], "categories": ["a", "b"]},
    {"tickets": [{"text": "x" * 5001}], "categories": ["a", "b"]},
    {"tickets": [{"text": "x"}] * 51, "categories": ["a", "b"]},
])
def test_triage_rejects_invalid_input(client, payload):
    assert client.post("/api/triage", json=payload).status_code == 422


def test_default_label_set_is_offered(client):
    sets = client.get("/api/label-sets").json()
    assert "Support client" in sets
    assert "facturation" in sets["Support client"]["categories"]


def test_label_set_save_persist_and_delete(client):
    body = {"categories": ["rh", "it"], "priorities": ["haute", "basse"]}
    assert client.put("/api/label-sets/Mon équipe", json=body).status_code == 200
    assert client.get("/api/label-sets").json()["Mon équipe"] == body
    assert client.delete("/api/label-sets/Mon équipe").status_code == 204
    assert "Mon équipe" not in client.get("/api/label-sets").json()
    assert client.delete("/api/label-sets/Mon équipe").status_code == 404


def test_label_set_rejects_single_priority_and_blank_name(client):
    assert client.put("/api/label-sets/x", json={"categories": ["a", "b"], "priorities": ["p"]}).status_code == 422
    assert client.put("/api/label-sets/%20", json={"categories": ["a", "b"]}).status_code == 422


def test_label_too_long_is_rejected(client):
    payload = {"tickets": [{"text": "x"}], "categories": ["a", "b" * 101]}
    assert client.post("/api/triage", json=payload).status_code == 422


def test_label_sets_are_capped(client):
    body = {"categories": ["a", "b"]}
    for i in range(49):  # + le jeu par défaut = 50
        assert client.put(f"/api/label-sets/jeu{i}", json=body).status_code == 200
    assert client.put("/api/label-sets/de-trop", json=body).status_code == 409
    assert client.put("/api/label-sets/jeu0", json={"categories": ["c", "d"]}).status_code == 200


def test_corrupted_label_sets_file_is_kept_aside(client):
    path = label_set_store.path
    path.write_text("{pas du json", encoding="utf-8")
    assert "Support client" in client.get("/api/label-sets").json()
    assert path.with_suffix(".corrompu").read_text(encoding="utf-8") == "{pas du json"
