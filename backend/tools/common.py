"""Lecture des fichiers CSV de tickets et des jeux de catégories, partagée par les outils."""
import csv
import re
import unicodedata
from pathlib import Path

TEXT_COLUMNS = ("texte", "text", "message", "description", "ticket", "contenu", "body")
CATEGORY_COLUMNS = ("categorie", "category", "label", "etiquette")
PRIORITY_COLUMNS = ("priorite", "priority")
ID_COLUMNS = ("id", "numero", "reference")
VIP_COLUMNS = ("vip", "client_vip")
AGE_COLUMNS = ("anciennete_jours", "age_jours", "anciennete", "age")
TRUE_VALUES = {"1", "oui", "o", "yes", "y", "true", "vrai", "x"}
# Statuts de l'export de l'interface : seuls les tickets relus par un humain servent à entraîner
VALIDATED_STATUSES = {"valide", "corrige"}


def _key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.strip().casefold())
    return re.sub(r"[^a-z0-9_]+", "_", "".join(c for c in folded if not unicodedata.combining(c))).strip("_")


def _clean_cell(value: str | None) -> str:
    value = (value or "").strip()
    # L'export de l'interface préfixe d'une apostrophe les cellules qui ressembleraient à une formule
    return value[1:] if value[:1] == "'" and value[1:2] in ("=", "+", "-", "@") else value


def read_tickets(path: Path, only_validated: bool = False) -> list[dict]:
    """Lit un CSV (séparateur « ; » ou « , »). Retourne des dictionnaires : id, text, category, priority, vip, age_days."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    header = raw.splitlines()[0] if raw.strip() else ""
    delimiter = max((";", ",", chr(9)), key=header.count)  # le séparateur le plus fréquent dans l'en-tête
    reader = csv.DictReader(raw.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("Fichier vide.")
    columns = {_key(name): name for name in reader.fieldnames}

    def find(options):
        return next((columns[o] for o in options if o in columns), None)

    text_col, cat_col = find(TEXT_COLUMNS), find(CATEGORY_COLUMNS)
    prio_col, id_col = find(PRIORITY_COLUMNS), find(ID_COLUMNS)
    vip_col, age_col = find(VIP_COLUMNS), find(AGE_COLUMNS)
    status_col = columns.get("statut") or columns.get("status")
    if not text_col:
        raise ValueError(f"Colonne du texte introuvable (attendu : {', '.join(TEXT_COLUMNS)}).")

    rows = []
    for index, record in enumerate(reader, start=1):
        text = _clean_cell(record.get(text_col))
        if not text:
            continue
        if only_validated and status_col and _key(_clean_cell(record.get(status_col))) not in VALIDATED_STATUSES:
            continue
        age = _clean_cell(record.get(age_col)) if age_col else ""
        rows.append({
            "id": _clean_cell(record.get(id_col)) if id_col else str(index),
            "text": text,
            "category": _clean_cell(record.get(cat_col)) if cat_col else "",
            "priority": _clean_cell(record.get(prio_col)) if prio_col else "",
            "vip": _clean_cell(record.get(vip_col)).casefold() in TRUE_VALUES if vip_col else False,
            "age_days": int(age) if age.isdigit() else None,
        })
    return rows


def load_label_set(name: str) -> dict:
    """Jeu enregistré (ou jeu par défaut) sous forme de dictionnaire."""
    from app.services.label_sets import label_set_store

    sets = label_set_store.list()
    if name not in sets:
        raise SystemExit(f"Jeu « {name} » introuvable. Jeux disponibles : {', '.join(sets) or 'aucun'}.")
    return sets[name].model_dump()
