import os
import sys
import types
from pathlib import Path

# Rend le package `app` importable quand pytest est lancé depuis backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# TestClient envoie « Host: testserver » : ce nom n'est accepté qu'ici, jamais dans les valeurs
# par défaut de l'application (voir app/security.py).
os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

# Remplace le service d'IA par un faux pour ne pas charger le vrai modèle (lourd)
_fake_service_module = types.ModuleType("app.services.ai_service")
_fake_service_module.ai_service = types.SimpleNamespace(
    predict_label=lambda text, labels, hypothesis_template=None: {
        "text": text,
        "predicted_label": labels[0],
        "confidence_score": 1.0,
    }
)
sys.modules["app.services.ai_service"] = _fake_service_module


def auth_headers() -> dict:
    """En-tête d'authentification valide pour les tests des routes protégées."""
    from app import auth

    return {"Authorization": f"Bearer {auth.issue_token()}"}
