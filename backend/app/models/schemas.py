from pydantic import BaseModel

class PredictRequest(BaseModel):
    text: str
    candidate_labels: list[str]

class PredictResponse(BaseModel):
    text: str
    predicted_label: str
    confidence_score: float