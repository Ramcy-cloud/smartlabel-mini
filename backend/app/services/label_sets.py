import json
import os
import threading
from pathlib import Path

from app.models.schemas import LabelSet

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "label_sets.json"

MAX_LABEL_SETS = 50


class TooManyLabelSets(Exception):
    pass


# Jeu proposé au premier lancement
DEFAULT_SETS = {
    "Support client": {
        "categories": ["facturation", "livraison", "panne technique", "compte et accès", "réclamation", "autre"],
        "priorities": ["urgente", "normale", "basse"],
        "urgent_keywords": [],
        # Une panne ou une réclamation n'est jamais de priorité basse
        "floors": {"panne technique": "normale", "réclamation": "normale"},
    }
}


class LabelSetStore:
    """Jeux de catégories enregistrés, persistés dans un fichier JSON (partagé par l'équipe)."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or os.getenv("LABEL_SETS_PATH") or DEFAULT_PATH)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        if not self.path.exists():
            return dict(DEFAULT_SETS)
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fichier corrompu : on le met de côté (jamais écrasé) et on repart des jeux par défaut
            self.path.replace(self.path.with_suffix(".corrompu"))
            return dict(DEFAULT_SETS)

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> dict[str, LabelSet]:
        with self._lock:
            return {name: LabelSet(**value) for name, value in self._read().items()}

    def save(self, name: str, label_set: LabelSet) -> None:
        with self._lock:
            data = self._read()
            if name not in data and len(data) >= MAX_LABEL_SETS:
                raise TooManyLabelSets()
            data[name] = label_set.model_dump()
            self._write(data)

    def delete(self, name: str) -> bool:
        with self._lock:
            data = self._read()
            if name not in data:
                return False
            del data[name]
            self._write(data)
            return True


label_set_store = LabelSetStore()
