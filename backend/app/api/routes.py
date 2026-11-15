import threading
from contextlib import contextmanager, nullcontext

from fastapi import APIRouter, HTTPException, Path, Query
from app.services.classifiers import ClassifierError, EngineUnavailable, UnknownEngine, describe_engines, get_engine
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

# Nombre de requêtes d'IA admises à attendre leur tour. Starlette exécute les routes synchrones
# — ici toutes, y compris la connexion et la dépendance qui vérifie le jeton — dans un pool de
# 40 threads. Sans cette borne, 40 requêtes d'IA simultanées occupent les 40 threads à attendre
# le verrou et plus aucune route ne répond, pas même /api/login. La limite par adresse IP ne
# protège pas de cela : elle borne un débit, pas un nombre de requêtes en vol.
MAX_WAITING_INFERENCES = 8
_inference_slots = threading.Semaphore(MAX_WAITING_INFERENCES)


@contextmanager
def _inference_slot():
    """Réserve une place dans la file d'inférence, ou refuse tout de suite.

    Le refus est immédiat et ne consomme pas de thread : c'est ce qui laisse le serveur répondre
    aux autres routes pendant une pointe de charge. Une place est prise par requête et non par
    ticket : un lot de 50 tickets occupe une seule place, et garde le verrou ticket par ticket
    pour que les prédictions s'entrelacent avec celles des autres requêtes.
    """
    if not _inference_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="Le serveur traite déjà le maximum d'analyses simultanées, réessayez dans un instant.",
            headers={"Retry-After": "30"},
        )
    try:
        yield
    finally:
        _inference_slots.release()


# Fonction synchrone (pas async) : l'inférence bloque le thread qui l'exécute, et FastAPI
# n'exécute une route synchrone que dans un thread du pool, jamais dans la boucle d'événements.
@router.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    # Chargé à l'usage, comme dans classifiers.py : le modèle est lourd et n'est pas utile
    # au démarrage ni aux moteurs « trained » et « mistral ».
    from app.services.ai_service import ai_service

    # Appel direct au service d'IA avec le texte et la liste des labels possibles
    with _inference_slot(), _inference_lock:  # une place dans la file, puis une inférence à la fois
        return ai_service.predict_label(request.text, request.candidate_labels)


# Fonction synchrone (pas async) : FastAPI l'exécute dans un thread et ne bloque pas le serveur pendant l'IA
@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest):
    """Propose une catégorie par le moteur choisi, et une priorité par des règles explicites, pour chaque ticket."""
    try:
        engine = get_engine(request.engine, request.categories)
    except UnknownEngine:
        raise HTTPException(status_code=422, detail="Moteur inconnu.")
    except EngineUnavailable:
        raise HTTPException(status_code=409, detail=f"Le moteur « {request.engine} » n'est pas disponible pour ces catégories.")

    # Une seule place pour tout le lot, prise avant la première inférence : un refus arrive donc
    # avant tout travail, et jamais au milieu d'un lot à moitié analysé.
    with _inference_slot() if engine.uses_cpu_model else nullcontext():
        return TriageResponse(results=_classify_all(engine, request))


def _classify_all(engine, request: TriageRequest) -> list[TriageResult]:
    results = []
    for ticket in request.tickets:
        error = None
        try:
            if engine.uses_cpu_model:
                with _inference_lock:
                    prediction = engine.classify(ticket.text, request.categories, request.descriptions)
            else:
                prediction = engine.classify(ticket.text, request.categories, request.descriptions)
        except ClassifierError as failure:
            if failure.fatal:
                raise HTTPException(status_code=502, detail=str(failure))
            # Ticket non classé : à traiter à la main (confiance nulle, donc « à relire »)
            error, prediction = str(failure), None
        item = TriageResult(
            id=ticket.id,
            text=ticket.text,
            category=prediction.category if prediction else request.categories[0],
            category_confidence=prediction.confidence if prediction else 0.0,
            engine=engine.name,
            engine_error=error,
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
    return results


@router.get("/engines")
def list_engines(categories: list[str] = Query(default=[])):
    """Moteurs de classification proposés, avec leur disponibilité pour ces catégories."""
    return describe_engines(categories)


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
