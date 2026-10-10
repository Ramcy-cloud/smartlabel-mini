from pydantic import BaseModel, Field, field_validator, model_validator

class PredictRequest(BaseModel):
    text: str
    candidate_labels: list[str]

class PredictResponse(BaseModel):
    text: str
    predicted_label: str
    confidence_score: float

MAX_TICKET_CHARS = 5000
MAX_TICKETS_PER_REQUEST = 50
MAX_LABELS = 20
MAX_LABEL_CHARS = 100


def _clean_labels(labels: list[str]) -> list[str]:
    cleaned = []
    for label in labels:
        label = label.strip()
        if not label:
            raise ValueError("Un libellé ne peut pas être vide.")
        if len(label) > MAX_LABEL_CHARS:
            raise ValueError(f"Un libellé ne peut pas dépasser {MAX_LABEL_CHARS} caractères.")
        if label.casefold() in {c.casefold() for c in cleaned}:
            raise ValueError(f"Libellé en double : {label}")
        cleaned.append(label)
    return cleaned


class Ticket(BaseModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=MAX_TICKET_CHARS)


class TriageRequest(BaseModel):
    tickets: list[Ticket] = Field(min_length=1, max_length=MAX_TICKETS_PER_REQUEST)
    categories: list[str] = Field(min_length=2, max_length=MAX_LABELS)
    priorities: list[str] | None = Field(default=None, min_length=2, max_length=MAX_LABELS)

    @field_validator("categories", "priorities")
    @classmethod
    def clean(cls, labels):
        return None if labels is None else _clean_labels(labels)


class TriageResult(BaseModel):
    id: str | None
    text: str
    category: str
    category_confidence: float
    priority: str | None = None
    priority_confidence: float | None = None


class TriageResponse(BaseModel):
    results: list[TriageResult]


class LabelSet(BaseModel):
    categories: list[str] = Field(min_length=2, max_length=MAX_LABELS)
    priorities: list[str] = Field(default_factory=list, max_length=MAX_LABELS)

    @field_validator("categories", "priorities")
    @classmethod
    def clean(cls, labels):
        return _clean_labels(labels)

    @model_validator(mode="after")
    def priorities_need_two(self):
        if len(self.priorities) == 1:
            raise ValueError("Indiquez au moins deux priorités, ou aucune.")
        return self
