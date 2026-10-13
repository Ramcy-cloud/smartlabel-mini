"""Moteurs de classification des tickets : une même interface, trois façons de choisir la catégorie.

- « zero-shot » : modèle local, aucune donnée ne quitte la machine.
- « trained »   : petit classifieur entraîné sur vos propres tickets validés (local).
- « mistral »   : API Mistral (cloud), seulement si une clé est configurée. Les textes quittent la machine.
"""
import os
from dataclasses import dataclass


class ClassifierError(Exception):
    """Un moteur n'a pas pu classer un ticket. `fatal` : inutile de continuer le lot (clé refusée, par exemple)."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


class UnknownEngine(Exception):
    pass


class EngineUnavailable(Exception):
    pass


@dataclass
class Prediction:
    category: str
    confidence: float


DEFAULT_TEMPLATE = "Ce texte concerne : {}."


def hypothesis_template() -> str:
    """Phrase testée par le modèle zero-shot pour chaque catégorie (HYPOTHESIS_TEMPLATE, doit contenir {})."""
    template = os.getenv("HYPOTHESIS_TEMPLATE", "").strip()
    return template if "{}" in template else DEFAULT_TEMPLATE


def model_labels(categories: list[str], descriptions: dict[str, str] | None) -> list[str]:
    """Ce que voit le modèle pour chaque catégorie : sa description si elle existe, sinon son nom."""
    descriptions = descriptions or {}
    return [descriptions.get(category) or category for category in categories]


class ZeroShotEngine:
    name = "zero-shot"
    label = "Local (zero-shot)"
    sends_data_outside = False
    uses_cpu_model = True

    def available(self) -> bool:
        return True

    def available_for(self, categories: list[str]) -> bool:
        return True

    def classify(self, text: str, categories: list[str], descriptions: dict[str, str] | None = None) -> Prediction:
        from app.services.ai_service import ai_service  # chargé à l'usage : le modèle est lourd

        labels = model_labels(categories, descriptions)
        result = ai_service.predict_label(text, labels, hypothesis_template=hypothesis_template())
        return Prediction(categories[labels.index(result["predicted_label"])], float(result["confidence_score"]))


def _engines() -> dict:
    from app.services.mistral_engine import MistralEngine
    from app.services.trained_engine import TrainedEngine

    return {"zero-shot": ZeroShotEngine(), "trained": TrainedEngine(), "mistral": MistralEngine()}


def get_engine(name: str, categories: list[str]):
    engines = _engines()
    if name not in engines:
        raise UnknownEngine(name)
    engine = engines[name]
    if not engine.available_for(categories):
        raise EngineUnavailable(name)
    return engine


def describe_engines(categories: list[str] | None = None) -> list[dict]:
    """Moteurs proposés à l'interface, avec leur disponibilité pour ces catégories."""
    result = []
    for engine in _engines().values():
        info = {
            "name": engine.name,
            "label": engine.label,
            "sends_data_outside": engine.sends_data_outside,
            "available": engine.available_for(categories or []),
        }
        if hasattr(engine, "describe"):
            info.update(engine.describe(categories or []))
        result.append(info)
    return result
