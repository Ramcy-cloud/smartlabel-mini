import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import auth_headers
from app.main import create_app
from app.services import trained_engine
from app.services.label_sets import label_set_store

CATEGORIES = ["facturation", "livraison", "autre"]


class FakeEmbedder:
    """Vecteurs de mots simples : deux textes avec les mêmes mots ont des vecteurs proches."""

    VOCAB = ["facture", "prélevé", "colis", "livraison", "retard", "bonjour", "merci", "remboursement", "payé", "arrivé"]

    def encode(self, texts):
        vectors = []
        for text in texts:
            words = text.casefold().replace(",", " ").replace(".", " ").split()
            v = np.array([float(sum(w.startswith(k) for w in words)) for k in self.VOCAB]) + 1e-3
            vectors.append(v / np.linalg.norm(v))
        return np.array(vectors)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(label_set_store, "path", tmp_path / "label_sets.json")
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("HYPOTHESIS_TEMPLATE", raising=False)
    monkeypatch.setattr(trained_engine, "_embedder", FakeEmbedder())
    return TestClient(create_app(), headers=auth_headers())


def write_model(tmp_path, categories=CATEGORIES, name="test", **overrides):
    dim = len(FakeEmbedder.VOCAB)
    rows = 1 if len(categories) == 2 else len(categories)
    coef = np.zeros((rows, dim))
    coef[0, 0] = 5.0  # « facture » pousse vers la première catégorie
    if rows > 1:
        coef[1, 2] = 5.0  # « colis » vers la deuxième
    data = dict(categories=categories, coef=coef, intercept=np.zeros(rows), n_samples=30,
                class_counts={c: 10 for c in categories}, cv_accuracy=0.8, name=name)
    data.update(overrides)
    trained_engine.save_model(tmp_path / "models" / f"{name}.json", **data)


# ------------------------------------------------------------------ zero-shot : descriptions et gabarit
def test_zero_shot_sends_descriptions_and_maps_back_to_category_names(client, monkeypatch):
    from app.services import ai_service

    seen = {}

    def spy(text, labels, hypothesis_template=None):
        seen.update(labels=labels, template=hypothesis_template)
        return {"text": text, "predicted_label": labels[1], "confidence_score": 0.9}

    monkeypatch.setattr(ai_service.ai_service, "predict_label", spy)
    res = client.post("/api/triage", json={
        "tickets": [{"text": "x"}], "categories": CATEGORIES,
        "descriptions": {"livraison": "colis en retard ou perdu"},
    })
    assert res.status_code == 200
    assert seen["labels"] == ["facturation", "colis en retard ou perdu", "autre"]
    assert res.json()["results"][0]["category"] == "livraison"  # le nom, pas la description
    assert seen["template"] == "Ce texte concerne : {}."


def test_template_can_be_changed_by_environment_but_must_contain_a_placeholder(client, monkeypatch):
    from app.services import ai_service, classifiers

    monkeypatch.setenv("HYPOTHESIS_TEMPLATE", "Sujet : {}.")
    assert classifiers.hypothesis_template() == "Sujet : {}."
    monkeypatch.setenv("HYPOTHESIS_TEMPLATE", "pas de marque")
    assert classifiers.hypothesis_template() == classifiers.DEFAULT_TEMPLATE


@pytest.mark.parametrize("descriptions", [
    {"inconnue": "x"},
    {"facturation": "colis"} | {"livraison": "colis"},
    {"facturation": "livraison"},  # reprend le nom d'une autre catégorie
    {"facturation": "x" * 201},
])
def test_invalid_descriptions_are_rejected(client, descriptions):
    body = {"tickets": [{"text": "x"}], "categories": CATEGORIES, "descriptions": descriptions}
    assert client.post("/api/triage", json=body).status_code == 422
    assert client.put("/api/label-sets/t", json={"categories": CATEGORIES, "descriptions": descriptions}).status_code == 422


def test_blank_descriptions_are_dropped_and_sets_keep_them(client):
    body = {"categories": CATEGORIES, "descriptions": {"facturation": "  problème de facture  ", "autre": "   "}}
    assert client.put("/api/label-sets/t", json=body).json()["descriptions"] == {"facturation": "problème de facture"}
    assert client.get("/api/label-sets").json()["t"]["descriptions"] == {"facturation": "problème de facture"}


def test_default_set_comes_with_descriptions_for_every_category(client):
    default = client.get("/api/label-sets").json()["Support client"]
    assert set(default["descriptions"]) == set(default["categories"])


# ------------------------------------------------------------------ moteurs
def test_engines_listing(client, tmp_path):
    engines = {e["name"]: e for e in client.get("/api/engines", params={"categories": CATEGORIES}).json()}
    assert engines["zero-shot"]["available"] and not engines["zero-shot"]["sends_data_outside"]
    assert engines["trained"]["available"] is False and engines["mistral"]["available"] is False
    write_model(tmp_path)
    engines = {e["name"]: e for e in client.get("/api/engines", params={"categories": CATEGORIES}).json()}
    assert engines["trained"]["available"] is True and engines["trained"]["models"][0]["cv_accuracy"] == 0.8
    other = {e["name"]: e for e in client.get("/api/engines", params={"categories": ["a", "b"]}).json()}
    assert other["trained"]["available"] is False  # un modèle ne vaut que pour exactement ses catégories


@pytest.mark.parametrize("engine,status", [("inconnu", 422), ("mistral", 409), ("trained", 409)])
def test_unknown_or_unavailable_engines_are_refused(client, engine, status):
    res = client.post("/api/triage", json={"tickets": [{"text": "x"}], "categories": CATEGORIES, "engine": engine})
    assert res.status_code == status


# ------------------------------------------------------------------ moteur entraîné
def test_trained_engine_classifies_with_probabilities(client, tmp_path):
    write_model(tmp_path)
    res = client.post("/api/triage", json={
        "tickets": [{"text": "Ma facture est fausse, facture prélevée"}, {"text": "Mon colis est arrivé"}],
        "categories": CATEGORIES, "engine": "trained",
    })
    assert res.status_code == 200
    first, second = res.json()["results"]
    assert (first["category"], second["category"]) == ("facturation", "livraison")
    assert first["engine"] == "trained" and 1 / 3 < first["category_confidence"] <= 1


def test_trained_model_can_have_the_same_categories_in_another_order(client, tmp_path):
    write_model(tmp_path, categories=["autre", "facturation", "livraison"])
    res = client.post("/api/triage", json={"tickets": [{"text": "facture"}], "categories": CATEGORIES, "engine": "trained"})
    assert res.status_code == 200 and res.json()["results"][0]["category"] == "autre"


def test_binary_model(client, tmp_path):
    write_model(tmp_path, categories=["a", "b"], name="bin")
    res = client.post("/api/triage", json={"tickets": [{"text": "facture"}], "categories": ["a", "b"], "engine": "trained"})
    assert res.status_code == 200
    assert 0.5 <= res.json()["results"][0]["category_confidence"] <= 1


def test_embedder_mismatch_is_reported_per_ticket_not_as_a_crash(client, tmp_path, monkeypatch):
    write_model(tmp_path)

    class Wrong:
        def encode(self, texts):
            return np.ones((len(texts), 7))

    monkeypatch.setattr(trained_engine, "_embedder", Wrong())
    res = client.post("/api/triage", json={"tickets": [{"text": "x"}], "categories": CATEGORIES, "engine": "trained"})
    assert res.status_code == 200 and "entraînement" in res.json()["results"][0]["engine_error"]


# ------------------------------------------------------------------ fichiers de modèle : jamais de code, validation stricte
GOOD = {"version": 1, "categories": ["a", "b", "c"], "coef": [[0.0] * 4] * 3, "intercept": [0.0] * 3}


@pytest.mark.parametrize("change", [
    {"version": 2}, {"categories": ["a"]}, {"categories": ["a", "A", "c"]}, {"categories": ["a", "", "c"]}, {"categories": ["a", 3, "c"]},
    {"coef": [[0.0] * 4] * 2}, {"coef": [[0.0, float("nan"), 0.0, 0.0]] * 3}, {"coef": [[float("inf")] * 4] * 3},
    {"intercept": [0.0] * 2}, {"coef": "texte"}, {"coef": []}, {"coef": [[0.0] * 5000] * 3},
])
def test_invalid_models_are_rejected(change):
    with pytest.raises(trained_engine.InvalidModel):
        trained_engine.validate_model({**GOOD, **change})


def test_missing_keys_are_rejected():
    with pytest.raises(trained_engine.InvalidModel):
        trained_engine.validate_model({"version": 1})


def test_bad_files_are_ignored_and_never_executed(client, tmp_path, caplog):
    write_model(tmp_path, name="bon")
    models = tmp_path / "models"
    (models / "casse.json").write_text("{pas du json", encoding="utf-8")
    (models / "piege.json").write_text(json.dumps({**GOOD, "__import__": "os", "coef": "x"}), encoding="utf-8")
    (models / "pickle.json").write_bytes(b"\x80\x04\x95cos\nsystem\n")
    found = trained_engine.load_models()
    assert [m["name"] for m in found] == ["bon"]


def test_oversized_model_files_are_ignored(tmp_path, monkeypatch):
    write_model(tmp_path, name="gros")
    monkeypatch.setattr(trained_engine, "MAX_MODEL_BYTES", 10)
    assert trained_engine.load_models(tmp_path / "models") == []


def test_the_most_recent_model_wins(client, tmp_path):
    write_model(tmp_path, name="ancien")
    path = tmp_path / "models" / "ancien.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["trained_at"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(data), encoding="utf-8")
    write_model(tmp_path, name="recent", n_samples=99)
    assert trained_engine.TrainedEngine._find(CATEGORIES)["n_samples"] == 99
