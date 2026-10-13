"""Mesure la précision du tri sur des tickets dont on connaît la bonne catégorie.

Exemple :
    python -m tools.evaluate tools/exemples/tickets_exemple.csv --set "Support client"
    python -m tools.evaluate mes_tickets.csv --set "Support client" --engine trained --errors erreurs.csv

Le fichier CSV doit contenir le texte du ticket et la bonne catégorie (colonnes « texte » et « categorie »).
Facultatif : « priorite » (bonne priorité), « vip », « anciennete_jours », « id ».
"""
import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.common import load_label_set, read_tickets  # noqa: E402

BIN_EDGES = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]


# --------------------------------------------------------------------------- calculs (fonctions pures)
def accuracy(rows: list[dict]) -> float:
    return sum(r["expected"] == r["predicted"] for r in rows) / len(rows) if rows else 0.0


def per_category(rows: list[dict], categories: list[str]) -> list[dict]:
    result = []
    for category in categories:
        tp = sum(r["expected"] == category and r["predicted"] == category for r in rows)
        predicted = sum(r["predicted"] == category for r in rows)
        expected = sum(r["expected"] == category for r in rows)
        precision = tp / predicted if predicted else 0.0
        recall = tp / expected if expected else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        result.append({"category": category, "precision": precision, "recall": recall, "f1": f1, "support": expected})
    return result


def confusion(rows: list[dict], categories: list[str]) -> dict[str, Counter]:
    matrix = {c: Counter() for c in categories}
    for r in rows:
        matrix.setdefault(r["expected"], Counter())[r["predicted"]] += 1
    return matrix


def calibration(rows: list[dict]) -> list[dict]:
    """Exactitude par tranche de confiance : une confiance de 90 % doit correspondre à ~90 % de bonnes réponses."""
    bins = []
    for low, high in zip(BIN_EDGES, BIN_EDGES[1:]):
        group = [r for r in rows if low <= r["confidence"] < high]
        bins.append({"low": low, "high": min(high, 1.0), "count": len(group), "accuracy": accuracy(group) if group else None})
    return bins


def at_threshold(rows: list[dict], threshold: float) -> dict:
    accepted = [r for r in rows if r["confidence"] >= threshold]
    return {
        "threshold": threshold,
        "coverage": len(accepted) / len(rows) if rows else 0.0,
        "accepted": len(accepted),
        "accuracy": accuracy(accepted) if accepted else None,
    }


def recommend_threshold(rows: list[dict], target: float = 0.9, min_accepted: int = 10) -> dict | None:
    """Plus petit seuil de confiance dont les tickets acceptés atteignent la précision visée."""
    for threshold in sorted({r["confidence"] for r in rows}):
        result = at_threshold(rows, threshold)
        if result["accepted"] >= min_accepted and result["accuracy"] is not None and result["accuracy"] >= target:
            return result
    return None


def priority_report(rows: list[dict], top_priority: str | None) -> dict | None:
    judged = [r for r in rows if r.get("expected_priority")]
    if not judged:
        return None
    exact = sum(r["expected_priority"] == r["priority"] for r in judged) / len(judged)
    top = [r for r in judged if top_priority and r["expected_priority"] == top_priority]
    top_recall = sum(r["priority"] == top_priority for r in top) / len(top) if top else None
    wrongly_top = sum(r["priority"] == top_priority and r["expected_priority"] != top_priority for r in judged) if top_priority else 0
    return {"count": len(judged), "exact": exact, "top_recall": top_recall, "top_count": len(top), "wrongly_top": wrongly_top}


# --------------------------------------------------------------------------- exécution
def run_engine(tickets: list[dict], label_set: dict, engine_name: str) -> list[dict]:
    from app.services.classifiers import ClassifierError, get_engine
    from app.services.priority import compute_priority

    categories, descriptions, priorities = label_set["categories"], label_set["descriptions"], label_set["priorities"]
    engine = get_engine(engine_name, categories)
    rows = []
    for index, ticket in enumerate(tickets, start=1):
        try:
            prediction = engine.classify(ticket["text"], categories, descriptions)
            category, confidence = prediction.category, prediction.confidence
        except ClassifierError as error:
            if error.fatal:
                raise SystemExit(f"Arrêt : {error}")
            category, confidence = "(erreur)", 0.0
        row = {**ticket, "expected": ticket["category"], "predicted": category, "confidence": confidence,
               "expected_priority": ticket["priority"]}
        if priorities:
            row["priority"], _ = compute_priority(
                ticket["text"], priorities, category=category, extra_keywords=label_set["urgent_keywords"],
                floors=label_set["floors"], vip=ticket["vip"], age_days=ticket["age_days"],
            )
        rows.append(row)
        if index % 20 == 0:
            print(f"  {index}/{len(tickets)} tickets traités…", file=sys.stderr)
    return rows


def pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f} %"


def print_report(rows: list[dict], label_set: dict, args) -> None:
    categories = label_set["categories"]
    correct = sum(r["expected"] == r["predicted"] for r in rows)
    print(f"\nMoteur : {args.engine}   Tickets : {len(rows)}   Descriptions : {'oui' if label_set['descriptions'] else 'non'}")
    if args.engine == "zero-shot":
        from app.services.classifiers import hypothesis_template

        print(f"Gabarit : « {hypothesis_template()} »")
    print(f"\nExactitude globale : {pct(accuracy(rows))}  ({correct}/{len(rows)})")

    print("\nPar catégorie (précision = parmi les tickets proposés, % corrects ; rappel = parmi les vrais, % retrouvés) :")
    print(f"  {'catégorie':<18}{'précision':>10}{'rappel':>10}{'F1':>8}{'effectif':>10}")
    for line in per_category(rows, categories):
        print(f"  {line['category']:<18}{pct(line['precision']):>10}{pct(line['recall']):>10}{pct(line['f1']):>8}{line['support']:>10}")

    print("\nMatrice de confusion (lignes = attendu, colonnes = proposé) :")
    shown = categories + sorted({r["predicted"] for r in rows} - set(categories))
    print("  " + " " * 18 + "".join(f"{c[:9]:>10}" for c in shown))
    for category, counts in confusion(rows, categories).items():
        print(f"  {category:<18}" + "".join(f"{counts.get(c, 0):>10}" for c in shown))

    print("\nConfiance et exactitude (une confiance de 90 % devrait donner ~90 % de bonnes réponses) :")
    for b in calibration(rows):
        if b["count"]:
            print(f"  confiance {b['low'] * 100:3.0f}-{b['high'] * 100:3.0f} % : {b['count']:4d} tickets, exactitude {pct(b['accuracy'])}")

    print(f"\nAu seuil de relecture actuel ({args.threshold * 100:.0f} %) :")
    current = at_threshold(rows, args.threshold)
    print(f"  {pct(current['coverage'])} des tickets passent sans relecture, avec une exactitude de {pct(current['accuracy'])}.")
    best = recommend_threshold(rows, args.target)
    if best:
        print(f"  Seuil conseillé pour {args.target * 100:.0f} % de précision : {best['threshold'] * 100:.0f} % "
              f"({pct(best['coverage'])} des tickets passent sans relecture).")
    else:
        print(f"  Aucun seuil n'atteint {args.target * 100:.0f} % de précision : relire tout, ou améliorer le moteur.")

    priority = priority_report(rows, (label_set["priorities"] or [None])[0])
    if priority:
        print(f"\nPriorité (règles) sur {priority['count']} tickets étiquetés : {pct(priority['exact'])} identiques à l'attendu.")
        if priority["top_recall"] is not None:
            print(f"  Urgences retrouvées : {pct(priority['top_recall'])} ({priority['top_count']} attendues) ; "
                  f"fausses urgences : {priority['wrongly_top']}.")

    errors = [r for r in rows if r["expected"] != r["predicted"]]
    if errors:
        print(f"\n{len(errors)} erreurs. Les plus confiantes (les plus dangereuses) :")
        for r in sorted(errors, key=lambda r: -r["confidence"])[:5]:
            print(f"  [{r['confidence'] * 100:3.0f} %] attendu « {r['expected']} », proposé « {r['predicted']} » : {r['text'][:80]}")
    if args.errors:
        with open(args.errors, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["id", "texte", "attendu", "propose", "confiance"])
            for r in errors:
                writer.writerow([r["id"], r["text"], r["expected"], r["predicted"], round(r["confidence"], 4)])
        print(f"\nErreurs enregistrées dans {args.errors}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mesure la précision du tri de tickets.")
    parser.add_argument("csv", type=Path, help="CSV de tickets avec la bonne catégorie")
    parser.add_argument("--set", dest="set_name", default="Support client", help="jeu de catégories (défaut : Support client)")
    parser.add_argument("--engine", default="zero-shot", choices=["zero-shot", "trained", "mistral"])
    parser.add_argument("--template", help="gabarit du zero-shot, avec {} (remplace HYPOTHESIS_TEMPLATE)")
    parser.add_argument("--no-descriptions", action="store_true", help="n'envoie que les noms des catégories au modèle")
    parser.add_argument("--threshold", type=float, default=0.75, help="seuil de relecture à évaluer (défaut : 0.75)")
    parser.add_argument("--target", type=float, default=0.9, help="précision visée pour le seuil conseillé (défaut : 0.9)")
    parser.add_argument("--errors", type=Path, help="écrit les erreurs dans ce fichier CSV")
    args = parser.parse_args(argv)

    if args.template:
        os.environ["HYPOTHESIS_TEMPLATE"] = args.template
    label_set = load_label_set(args.set_name)
    if args.no_descriptions:
        label_set["descriptions"] = {}
    tickets = [t for t in read_tickets(args.csv) if t["category"]]
    if not tickets:
        raise SystemExit("Aucun ticket avec une catégorie attendue dans ce fichier.")
    unknown = {t["category"] for t in tickets} - set(label_set["categories"])
    if unknown:
        raise SystemExit(f"Catégories absentes du jeu « {args.set_name} » : {', '.join(sorted(unknown))}")
    print_report(run_engine(tickets, label_set, args.engine), label_set, args)


if __name__ == "__main__":
    main()
