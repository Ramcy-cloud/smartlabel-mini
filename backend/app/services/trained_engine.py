"""Moteur « entraîné » : un classifieur appris sur vos propres tickets validés.

Le texte est transformé en vecteur par un modèle d'embeddings multilingue, puis une régression logistique
(poids stockés dans un fichier JSON) choisit la catégorie. Le fichier est du JSON pur, jamais du pickle :
un fichier modifié ne peut pas exécuter de code, il est seulement refusé s'il est invalide.

L'entraînement se fait hors du serveur, avec `python -m tools.train` (voir le README).
"""
import json
import logging
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.services.classifiers import ClassifierError, Prediction

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "models"
EMBEDDER_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_MODEL_BYTES = 20 * 1024 * 1024
MODEL_VERSION = 1
# Le cache est indexé par (chemin, date de modification, taille) : chaque réentraînement ajoute une entrée.
# Sans plafond, un dossier réécrit souvent ferait croître la mémoire du serveur sans fin.
MAX_CACHED_MODELS = 20

log = logging.getLogger("uvicorn.error")


def models_dir() -> Path:
    return Path(os.getenv("MODELS_DIR") or DEFAULT_DIR)


# ----------------------------------------------------------------------------- embeddings
class SentenceEmbedder:
    """Charge le modèle d'embeddings au premier usage (il est lourd et téléchargé une fois)."""

    def __init__(self, name: str = EMBEDDER_NAME):
        self.name = name
        self._model = None
        self._lock = threading.Lock()

    def encode(self, texts: list[str]) -> np.ndarray:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.name)
            return np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype=np.float64)


_embedder = SentenceEmbedder()


def get_embedder():
    return _embedder


def set_embedder(embedder) -> None:
    """Remplace l'embedder (tests et entraînement avec un embedder de substitution)."""
    global _embedder
    _embedder = embedder


# ----------------------------------------------------------------------------- fichier modèle
class InvalidModel(ValueError):
    pass


def validate_model(data: dict) -> dict:
    """Vérifie strictement la structure d'un modèle chargé depuis le disque."""
    try:
        categories = data["categories"]
        coef = np.asarray(data["coef"], dtype=np.float64)
        intercept = np.asarray(data["intercept"], dtype=np.float64)
    except (KeyError, TypeError, ValueError):
        raise InvalidModel("structure invalide")
    if data.get("version") != MODEL_VERSION:
        raise InvalidModel("version inconnue")
    if not (isinstance(categories, list) and 2 <= len(categories) <= 20 and all(isinstance(c, str) and c for c in categories)):
        raise InvalidModel("catégories invalides")
    if len({c.casefold() for c in categories}) != len(categories):
        raise InvalidModel("catégories en double")
    rows = 1 if len(categories) == 2 else len(categories)
    if coef.ndim != 2 or coef.shape[0] != rows or coef.shape[1] < 1 or coef.shape[1] > 4096:
        raise InvalidModel("poids de forme invalide")
    if intercept.shape != (rows,):
        raise InvalidModel("biais de forme invalide")
    if not (np.isfinite(coef).all() and np.isfinite(intercept).all()):
        raise InvalidModel("valeurs non finies")
    return {**data, "_coef": coef, "_intercept": intercept}


def save_model(path: Path, *, categories, coef, intercept, n_samples, class_counts, cv_accuracy, name, embedder=EMBEDDER_NAME) -> None:
    data = {
        "version": MODEL_VERSION,
        "name": name,
        "embedder": embedder,
        "categories": list(categories),
        "coef": np.asarray(coef, dtype=float).tolist(),
        "intercept": np.asarray(intercept, dtype=float).tolist(),
        "n_samples": int(n_samples),
        "class_counts": {k: int(v) for k, v in class_counts.items()},
        "cv_accuracy": None if cv_accuracy is None else float(cv_accuracy),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    validate_model(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


_cache: dict[tuple, dict | None] = {}  # (chemin, date de modification, taille) -> modèle validé, ou None si invalide
_cache_lock = threading.Lock()


def _remember(key: tuple, value: dict | None) -> None:
    """Mémorise un modèle chargé et oublie les plus anciennes entrées au-delà du plafond."""
    with _cache_lock:
        _cache[key] = value
        while len(_cache) > MAX_CACHED_MODELS:
            del _cache[next(iter(_cache))]  # un dictionnaire garde l'ordre d'insertion


def _load_one(path: Path) -> dict | None:
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _cache:
        try:
            if stat.st_size > MAX_MODEL_BYTES:
                raise InvalidModel("fichier trop volumineux")
            _remember(key, {**validate_model(json.loads(path.read_text(encoding="utf-8"))), "_file": path.name})
        except (OSError, ValueError) as error:  # JSON invalide, structure invalide, fichier illisible
            log.warning("Modèle entraîné ignoré (%s) : %s", path.name, error)
            _remember(key, None)
    return _cache.get(key)


def load_models(directory: Path | None = None) -> list[dict]:
    """Modèles valides du dossier, du plus récent au plus ancien. Les fichiers invalides sont ignorés."""
    directory = Path(directory or models_dir())
    if not directory.is_dir():
        return []
    models = [m for m in (_load_one(path) for path in sorted(directory.glob("*.json"))) if m]
    return sorted(models, key=lambda m: m.get("trained_at", ""), reverse=True)


def predict_proba(model: dict, vector: np.ndarray) -> np.ndarray:
    coef, intercept = model["_coef"], model["_intercept"]
    if vector.shape != (coef.shape[1],):
        raise ClassifierError("Le modèle entraîné ne correspond pas au modèle d'embeddings actuel : relancez l'entraînement.")
    logits = coef @ vector + intercept
    if coef.shape[0] == 1:  # deux catégories : une seule sortie
        p1 = 1.0 / (1.0 + math.exp(-float(np.clip(logits[0], -500, 500))))
        return np.array([1.0 - p1, p1])
    logits = logits - logits.max()
    exp = np.exp(logits)
    return exp / exp.sum()


def public_info(model: dict) -> dict:
    return {
        "name": model.get("name") or model["_file"],
        "categories": model["categories"],
        "n_samples": model.get("n_samples"),
        "cv_accuracy": model.get("cv_accuracy"),
        "trained_at": model.get("trained_at"),
    }


# ----------------------------------------------------------------------------- moteur
class TrainedEngine:
    name = "trained"
    label = "Entraîné sur vos tickets"
    sends_data_outside = False
    uses_cpu_model = True

    @staticmethod
    def _find(categories: list[str]) -> dict | None:
        wanted = set(categories)
        return next((m for m in load_models() if set(m["categories"]) == wanted), None)

    def available(self) -> bool:
        return bool(load_models())

    def available_for(self, categories: list[str]) -> bool:
        return bool(categories) and self._find(categories) is not None

    def describe(self, categories: list[str]) -> dict:
        return {"models": [public_info(m) for m in load_models()]}

    def classify(self, text: str, categories: list[str], descriptions: dict[str, str] | None = None) -> Prediction:
        model = self._find(categories)
        if model is None:
            raise ClassifierError("Aucun modèle entraîné pour exactement ces catégories.", fatal=True)
        vector = get_embedder().encode([text])[0]
        probabilities = predict_proba(model, vector)
        best = int(np.argmax(probabilities))
        return Prediction(model["categories"][best], float(probabilities[best]))
