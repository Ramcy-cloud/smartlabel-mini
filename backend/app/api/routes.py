from fastapi import APIRouter, HTTPException, Path
from app.services.ai_service import ai_service
from app.services.label_sets import label_set_store
from app.models.schemas import (
    LabelSet,
    PredictRequest,
    PredictResponse,
    TriageRequest,
    TriageResponse,
    TriageResult,
)

router = APIRouter()

@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    # Appel direct au service d'IA avec le texte et la liste des labels possibles
    result = ai_service.predict_label(request.text, request.candidate_labels)
    return result


# Fonction synchrone (pas async) : FastAPI l'exécute dans un thread et ne bloque pas le serveur pendant l'IA
@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest):
    """Propose une catégorie (et une priorité si fournie) pour chaque ticket."""
    results = []
    for ticket in request.tickets:
        category = ai_service.predict_label(ticket.text, request.categories)
        item = TriageResult(
            id=ticket.id,
            text=ticket.text,
            category=category["predicted_label"],
            category_confidence=category["confidence_score"],
        )
        if request.priorities:
            priority = ai_service.predict_label(ticket.text, request.priorities)
            item.priority = priority["predicted_label"]
            item.priority_confidence = priority["confidence_score"]
        results.append(item)
    return TriageResponse(results=results)


@router.get("/label-sets", response_model=dict[str, LabelSet])
def list_label_sets():
    return label_set_store.list()


@router.put("/label-sets/{name}", response_model=LabelSet)
def save_label_set(label_set: LabelSet, name: str = Path(min_length=1, max_length=60)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Le nom du jeu ne peut pas être vide.")
    label_set_store.save(name, label_set)
    return label_set


@router.delete("/label-sets/{name}", status_code=204)
def delete_label_set(name: str = Path(min_length=1, max_length=60)):
    if not label_set_store.delete(name):
        raise HTTPException(status_code=404, detail="Jeu introuvable.")
