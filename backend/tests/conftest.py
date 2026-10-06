import sys
import types
from pathlib import Path

# Rend le package `app` importable quand pytest est lancé depuis backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Remplace le service d'IA par un faux pour ne pas charger le vrai modèle (lourd)
_fake_service_module = types.ModuleType("app.services.ai_service")
_fake_service_module.ai_service = types.SimpleNamespace(
    predict_label=lambda text, labels: {
        "text": text,
        "predicted_label": labels[0],
        "confidence_score": 1.0,
    }
)
sys.modules["app.services.ai_service"] = _fake_service_module
