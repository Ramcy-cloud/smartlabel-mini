from transformers import pipeline

class ZeroShotService:
    def __init__(self):
        # Initialisation du pipeline Zero-Shot Classification
        # joeddav/xlm-roberta-large-xnli : modèle multilingue (dont français et anglais) entraîné sur XNLI
        print("Chargement du modèle d'IA en cours...")
        self.classifier = pipeline("zero-shot-classification", model="joeddav/xlm-roberta-large-xnli")
        print("Modèle chargé et prêt !")

    def predict_label(self, text: str, candidate_labels: list[str], hypothesis_template: str | None = None) -> dict:
        # Le modèle évalue le texte par rapport aux labels proposés.
        # Le gabarit est la phrase testée pour chaque label (« This example is {}. » par défaut, en anglais).
        kwargs = {"hypothesis_template": hypothesis_template} if hypothesis_template else {}
        result = self.classifier(text, candidate_labels, **kwargs)
        
        # On extrait le label gagnant (celui avec le score de confiance le plus élevé)
        return {
            "text": text,
            "predicted_label": result["labels"][0],
            "confidence_score": round(result["scores"][0], 4)
        }

# On exporte une instance unique pour toute l'API
ai_service = ZeroShotService()