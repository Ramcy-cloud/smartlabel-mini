import csv
import json
from pathlib import Path

import numpy as np
import pytest

from app.models.schemas import LabelSet
from app.services import trained_engine
from app.services.label_sets import label_set_store
from tools import evaluate, train
from tools.common import read_tickets
from test_engines import FakeEmbedder  # noqa: E402  (module de tests voisin)


def rows(*items):
    """(attendu, proposé, confiance) -> lignes de résultats."""
    return [{"expected": e, "predicted": p, "confidence": c, "text": f"t{i}", "id": str(i)} for i, (e, p, c) in enumerate(items)]


# ------------------------------------------------------------------ calculs de mesure
def test_accuracy_and_per_category():
    data = rows(("a", "a", 0.9), ("a", "b", 0.6), ("b", "b", 0.8), ("b", "b", 0.7))
    assert evaluate.accuracy(data) == 0.75
    stats = {s["category"]: s for s in evaluate.per_category(data, ["a", "b"])}
    assert stats["a"]["precision"] == 1.0 and stats["a"]["recall"] == 0.5
    assert stats["b"]["precision"] == pytest.approx(2 / 3) and stats["b"]["recall"] == 1.0
    assert stats["a"]["support"] == 2 and 0 < stats["a"]["f1"] < 1


def test_empty_and_degenerate_cases_do_not_divide_by_zero():
    assert evaluate.accuracy([]) == 0.0
    stats = evaluate.per_category(rows(("a", "a", 0.9)), ["a", "zzz"])
    assert stats[1]["precision"] == 0.0 and stats[1]["recall"] == 0.0 and stats[1]["f1"] == 0.0
    assert evaluate.at_threshold([], 0.5)["accuracy"] is None


def test_confusion_matrix():
    matrix = evaluate.confusion(rows(("a", "a", 1), ("a", "b", 1), ("b", "b", 1)), ["a", "b"])
    assert matrix["a"] == {"a": 1, "b": 1} and matrix["b"] == {"b": 1}


def test_calibration_bins_cover_every_confidence_including_one():
    data = rows(("a", "a", 1.0), ("a", "b", 0.45), ("a", "a", 0.0))
    assert sum(b["count"] for b in evaluate.calibration(data)) == 3


def test_threshold_recommendation_picks_the_lowest_threshold_reaching_the_target():
    # Les réponses très confiantes sont justes, les peu confiantes se trompent souvent
    data = rows(*[("a", "a", 0.95)] * 12, *[("a", "b", 0.5)] * 6, *[("a", "a", 0.55)] * 2)
    best = evaluate.recommend_threshold(data, target=0.9, min_accepted=10)
    # Au seuil 0,50 on accepte aussi les 6 erreurs (70 % de précision) : le seuil retenu est donc 0,55
    assert evaluate.at_threshold(data, 0.5)["accuracy"] == pytest.approx(14 / 20)
    assert best["threshold"] == 0.55 and best["accuracy"] == 1.0 and best["coverage"] == pytest.approx(14 / 20)
    assert evaluate.recommend_threshold(rows(*[("a", "b", 0.9)] * 20), target=0.9) is None
    assert evaluate.recommend_threshold(rows(("a", "a", 0.9)), target=0.9, min_accepted=10) is None  # trop peu de tickets


def test_priority_report():
    data = [{"expected_priority": "urgente", "priority": "urgente"}, {"expected_priority": "urgente", "priority": "normale"},
            {"expected_priority": "basse", "priority": "urgente"}, {"expected_priority": "", "priority": "basse"}]
    report = evaluate.priority_report(data, "urgente")
    assert report["count"] == 3 and report["top_recall"] == 0.5 and report["wrongly_top"] == 1
    assert evaluate.priority_report([{"expected_priority": "", "priority": "x"}], "urgente") is None


# ------------------------------------------------------------------ lecture des CSV
def write_csv(path, text):
    path.write_text(text, encoding="utf-8-sig")
    return path


def test_read_tickets_handles_both_delimiters_accents_and_optional_columns(tmp_path):
    semi = write_csv(tmp_path / "a.csv", "id;texte;catégorie;Priorité;VIP;ancienneté_jours\nT1;Bonjour, ça va;autre;basse;oui;12\nT2;Autre;autre;;non;\n")
    comma = write_csv(tmp_path / "b.csv", "message,categorie\n\"Bonjour; ça va\",autre\n")
    first = read_tickets(semi)
    assert (first[0]["id"], first[0]["text"], first[0]["category"], first[0]["priority"], first[0]["vip"], first[0]["age_days"]) == ("T1", "Bonjour, ça va", "autre", "basse", True, 12)
    assert first[1]["vip"] is False and first[1]["age_days"] is None
    assert read_tickets(comma)[0]["text"] == "Bonjour; ça va"


def test_read_tickets_uses_only_validated_rows_of_an_interface_export(tmp_path):
    export = write_csv(tmp_path / "e.csv", "id;ticket;categorie;statut\n1;a;autre;validé\n2;b;autre;à relire\n3;c;autre;corrigé\n4;d;autre;sûr\n")
    assert [t["id"] for t in read_tickets(export, only_validated=True)] == ["1", "3"]
    assert len(read_tickets(export)) == 4


def test_export_protection_prefix_is_removed_when_reading_back(tmp_path):
    file = write_csv(tmp_path / "f.csv", "texte;categorie\n'=HYPERLINK(1);autre\n'bonjour;autre\n")
    assert [t["text"] for t in read_tickets(file)] == ["=HYPERLINK(1)", "'bonjour"]


def test_read_tickets_errors_are_clear(tmp_path):
    with pytest.raises(ValueError, match="texte"):
        read_tickets(write_csv(tmp_path / "x.csv", "colonne;autre\n1;2\n"))


def test_bundled_example_file_is_well_formed():
    tickets = read_tickets(Path(__file__).resolve().parent.parent / "tools" / "exemples" / "tickets_exemple.csv")
    assert len(tickets) == 144
    categories = {t["category"] for t in tickets}
    assert categories == {"facturation", "livraison", "panne technique", "compte et accès", "réclamation", "autre"}
    assert all(sum(t["category"] == c for t in tickets) == 24 for c in categories)
    assert {t["priority"] for t in tickets} == {"urgente", "normale", "basse"}
    assert len({t["id"] for t in tickets}) == 144


# ------------------------------------------------------------------ rapport complet (faux modèle)
def test_evaluate_prints_a_full_report_and_writes_errors(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(label_set_store, "path", tmp_path / "sets.json")
    errors = tmp_path / "erreurs.csv"
    evaluate.main([str(Path(__file__).resolve().parent.parent / "tools" / "exemples" / "tickets_exemple.csv"), "--errors", str(errors)])
    out = capsys.readouterr().out
    for fragment in ["Exactitude globale", "Par catégorie", "Matrice de confusion", "Confiance et exactitude", "seuil de relecture actuel", "Priorité (règles)"]:
        assert fragment in out
    with open(errors, encoding="utf-8-sig") as handle:
        assert len(list(csv.reader(handle, delimiter=";"))) > 100  # le faux modèle répond toujours la même catégorie


def test_evaluate_refuses_unknown_categories(tmp_path, monkeypatch):
    monkeypatch.setattr(label_set_store, "path", tmp_path / "sets.json")
    file = write_csv(tmp_path / "x.csv", "texte;categorie\nbonjour;inventée\n")
    with pytest.raises(SystemExit, match="absentes"):
        evaluate.main([str(file)])


# ------------------------------------------------------------------ entraînement
def labeled_file(tmp_path, per_class=12):
    lines = ["texte;categorie"]
    for i in range(per_class):
        lines += [f"facture prélevé remboursement payé {i};facturation", f"colis livraison retard arrivé {i};livraison", f"bonjour merci {i};autre"]
    return write_csv(tmp_path / "valides.csv", "\n".join(lines) + "\n")


def test_train_creates_a_model_that_matches_scikit_learn(tmp_path):
    pytest.importorskip("sklearn")
    texts = ["facture prélevé"] * 6 + ["colis retard"] * 6 + ["bonjour merci"] * 6
    labels = ["facturation"] * 6 + ["livraison"] * 6 + ["autre"] * 6
    classes, coef, intercept, cv = train.train(texts, labels, FakeEmbedder(), folds=3)
    assert classes == sorted(classes) and cv is not None and cv > 0.9
    # L'inférence du serveur (numpy) donne les mêmes probabilités que scikit-learn
    reference = train.fit(FakeEmbedder().encode(texts), labels, folds=3)
    assert list(reference.classes_) == classes and reference.coef_ == pytest.approx(coef)
    model = trained_engine.validate_model({"version": 1, "categories": classes, "coef": coef.tolist(), "intercept": intercept.tolist()})
    for text in ["facture prélevé", "colis retard", "bonjour"]:
        vector = FakeEmbedder().encode([text])[0]
        assert trained_engine.predict_proba(model, vector) == pytest.approx(reference.predict_proba([vector])[0], abs=1e-9)


def test_binary_inference_matches_scikit_learn():
    pytest.importorskip("sklearn")
    texts, labels = ["facture prélevé", "colis retard"] * 6, ["a", "b"] * 6
    x = FakeEmbedder().encode(texts)
    reference = train.fit(x, labels, folds=3)
    model = trained_engine.validate_model({"version": 1, "categories": list(reference.classes_), "coef": reference.coef_.tolist(), "intercept": reference.intercept_.tolist()})
    assert trained_engine.predict_proba(model, x[0]) == pytest.approx(reference.predict_proba([x[0]])[0], abs=1e-9)


def test_train_main_saves_json_and_the_engine_can_use_it(tmp_path, monkeypatch, capsys):
    pytest.importorskip("sklearn")
    monkeypatch.setattr(label_set_store, "path", tmp_path / "sets.json")
    monkeypatch.setattr(trained_engine, "_embedder", FakeEmbedder())
    label_set_store.save("Mini", LabelSet(categories=["facturation", "livraison", "autre"]))
    out = tmp_path / "models" / "mini.json"
    train.main([str(labeled_file(tmp_path)), "--set", "Mini", "--out", str(out)])
    assert "validation croisée" in capsys.readouterr().out
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["n_samples"] == 36 and "cv_accuracy" in data
    models = trained_engine.load_models(tmp_path / "models")
    assert models[0]["categories"] == sorted(["facturation", "livraison", "autre"])


def test_train_refuses_too_few_or_unknown_data(tmp_path, monkeypatch):
    monkeypatch.setattr(label_set_store, "path", tmp_path / "sets.json")
    monkeypatch.setattr(trained_engine, "_embedder", FakeEmbedder())
    small = write_csv(tmp_path / "petit.csv", "texte;categorie\nfacture;facturation\ncolis;livraison\n")
    with pytest.raises(SystemExit, match="Pas assez"):
        train.main([str(small), "--out", str(tmp_path / "m.json")])
    unknown = write_csv(tmp_path / "inconnu.csv", "texte;categorie\n" + "x;inventée\n" * 30)
    with pytest.raises(SystemExit, match="absentes"):
        train.main([str(unknown), "--out", str(tmp_path / "m.json")])


def test_train_ignores_unvalidated_tickets_of_an_export(tmp_path, monkeypatch):
    monkeypatch.setattr(label_set_store, "path", tmp_path / "sets.json")
    export = write_csv(tmp_path / "e.csv", "ticket;categorie;statut\n" + "x;facturation;à relire\n" * 30)
    with pytest.raises(SystemExit, match="Pas assez"):
        train.main([str(export), "--out", str(tmp_path / "m.json")])


def test_slug():
    assert train.slug("Support client") == "support-client" and train.slug("Équipe RH & IT !") == "equipe-rh-it" and train.slug("???") == "modele"
