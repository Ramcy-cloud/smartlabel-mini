from fastapi import APIRouter
from app.services.ai_service import ai_service
from app.models.schemas import PredictRequest, PredictResponse

router = APIRouter()

@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    # Appel direct au service d'IA avec le texte et la liste des labels possibles
    result = ai_service.predict_label(request.text, request.candidate_labels)
    return result