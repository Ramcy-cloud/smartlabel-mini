"""Entraîne un classifieur sur vos tickets validés (le moteur « trained » de l'application).

Exemple :
    python -m tools.train export_tickets.csv --set "Support client"

Le CSV peut être l'export de l'interface (seuls les tickets au statut « validé » ou « corrigé » sont utilisés,
puisque ce sont ceux qu'un humain a relus) ou un fichier avec les colonnes « texte » et « categorie ».
Nécessite scikit-learn : pip install -r requirements-tools.txt

Le modèle est enregistré en JSON dans backend/data/models (variable MODELS_DIR). Aucune donnée n'est envoyée en ligne.
Pour mesurer honnêtement la qualité, évaluez ensuite sur d'autres tickets que ceux de l'entraînement :
    python -m tools.evaluate autres_tickets.csv --engine trained
"""
import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.common import load_label_set, read_tickets  # noqa: E402

MIN_TICKETS = 20
MIN_PER_CATEGORY_WARNING = 10


def slug(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.casefold())
    return re.sub(r"[^a-z0-9]+", "-", "".join(c for c in folded if not unicodedata.combining(c))).strip("-") or "modele"


def train(texts: list[str], labels: list[str], embedder, folds: int = 5, seed: int = 0):
    """Entraîne la régression logistique. Retourne (classes, coef, intercept, précision en validation croisée)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    features = embedder.encode(texts)
    labels_array = np.asarray(labels)
    model = LogisticRegression(C=2.0, max_iter=2000, class_weight="balanced")

    cv_accuracy = None
    smallest = min(Counter(labels).values())
    if smallest >= 2:
        splits = StratifiedKFold(n_splits=min(folds, smallest), shuffle=True, random_state=seed)
        predicted = cross_val_predict(model, features, labels_array, cv=splits)
        cv_accuracy = float((predicted == labels_array).mean())

    model.fit(features, labels_array)
    return list(model.classes_), model.coef_, model.intercept_, cv_accuracy


def main(argv=None):
    parser = argparse.ArgumentParser(description="Entraîne un classifieur sur des tickets validés.")
    parser.add_argument("csv", type=Path, help="CSV de tickets validés (export de l'interface ou texte + categorie)")
    parser.add_argument("--set", dest="set_name", default="Support client", help="jeu de catégories (défaut : Support client)")
    parser.add_argument("--out", type=Path, help="fichier du modèle (défaut : backend/data/models/<jeu>.json)")
    parser.add_argument("--all-rows", action="store_true", help="utilise aussi les tickets non validés (déconseillé)")
    args = parser.parse_args(argv)

    from app.services import trained_engine

    label_set = load_label_set(args.set_name)
    tickets = [t for t in read_tickets(args.csv, only_validated=not args.all_rows) if t["category"]]
    unknown = {t["category"] for t in tickets} - set(label_set["categories"])
    if unknown:
        raise SystemExit(f"Catégories absentes du jeu « {args.set_name} » : {', '.join(sorted(unknown))}")
    counts = Counter(t["category"] for t in tickets)
    if len(tickets) < MIN_TICKETS or len(counts) < 2:
        raise SystemExit(
            f"Pas assez de tickets validés : {len(tickets)} sur {len(counts)} catégorie(s) "
            f"(minimum {MIN_TICKETS} tickets et 2 catégories). Validez-en davantage dans l'interface puis réexportez."
        )

    print(f"{len(tickets)} tickets, {len(counts)} catégories : " + ", ".join(f"{c} ({n})" for c, n in counts.most_common()))
    missing = [c for c in label_set["categories"] if counts[c] == 0]
    if missing:
        print(f"ATTENTION : aucune donnée pour {', '.join(missing)} : le moteur « trained » ne sera proposé que si le modèle "
              f"couvre exactement les catégories demandées.")
    few = [c for c, n in counts.items() if n < MIN_PER_CATEGORY_WARNING]
    if few:
        print(f"ATTENTION : moins de {MIN_PER_CATEGORY_WARNING} exemples pour {', '.join(few)} : résultats fragiles pour ces catégories.")

    classes, coef, intercept, cv = train([t["text"] for t in tickets], [t["category"] for t in tickets], trained_engine.get_embedder())
    out = args.out or trained_engine.models_dir() / f"{slug(args.set_name)}.json"
    trained_engine.save_model(
        out, categories=classes, coef=coef, intercept=intercept, n_samples=len(tickets),
        class_counts=counts, cv_accuracy=cv, name=args.set_name,
    )
    print(f"\nModèle enregistré : {out}")
    if cv is not None:
        print(f"Exactitude en validation croisée : {cv * 100:.1f} % (mesurée sur des tickets que le modèle n'a pas vus pendant l'entraînement).")
    print("Redémarrez ou rechargez l'interface : le moteur « Entraîné sur vos tickets » apparaît pour ces catégories.")


if __name__ == "__main__":
    main()
