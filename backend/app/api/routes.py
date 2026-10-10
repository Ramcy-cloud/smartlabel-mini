import threading

from fastapi import APIRouter, HTTPException, Path
from app.services.ai_service import ai_service
from app.services.priority import compute_priority
from app.services.label_sets import MAX_LABEL_SETS, TooManyLabelSets, label_set_store
from app.models.schemas import (
    LabelSet,
    PredictRequest,
    PredictResponse,
    TriageRequest,
    TriageResponse,
    TriageResult,
)

router = APIRouter()

# Le modèle tourne sur le processeur : une seule inférence à la fois, les autres requêtes patientent
_inference_lock = threading.Lock()

@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    # Appel direct au service d'IA avec le texte et la liste des labels possibles
    result = ai_service.predict_label(request.text, request.candidate_labels)
    return result


# Fonction synchrone (pas async) : FastAPI l'exécute dans un thread et ne bloque pas le serveur pendant l'IA
@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest):
    """Propose une catégorie par l'IA, et une priorité par des règles explicites, pour chaque ticket."""
    results = []
    for ticket in request.tickets:
        with _inference_lock:
            category = ai_service.predict_label(ticket.text, request.categories)
        item = TriageResult(
            id=ticket.id,
            text=ticket.text,
            category=category["predicted_label"],
            category_confidence=category["confidence_score"],
        )
        if request.priorities:
            item.priority, item.priority_reasons = compute_priority(
                ticket.text,
                request.priorities,
                category=item.category,
                extra_keywords=request.urgent_keywords,
                floors=request.floors,
                vip=ticket.vip,
                age_days=ticket.age_days,
            )
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
    try:
        label_set_store.save(name, label_set)
    except TooManyLabelSets:
        raise HTTPException(status_code=409, detail=f"Maximum {MAX_LABEL_SETS} jeux enregistrés : supprimez-en un d'abord.")
    return label_set


@router.delete("/label-sets/{name}", status_code=204)
def delete_label_set(name: str = Path(min_length=1, max_length=60)):
    if not label_set_store.delete(name):
        raise HTTPException(status_code=404, detail="Jeu introuvable.")
