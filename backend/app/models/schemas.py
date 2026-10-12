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
MAX_KEYWORDS = 50
MAX_KEYWORD_CHARS = 60


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


def _clean_keywords(keywords: list[str]) -> list[str]:
    cleaned = []
    for keyword in keywords:
        keyword = keyword.strip()
        if not keyword:
            continue
        if len(keyword) > MAX_KEYWORD_CHARS:
            raise ValueError(f"Un mot-clé ne peut pas dépasser {MAX_KEYWORD_CHARS} caractères.")
        if keyword.casefold() not in {k.casefold() for k in cleaned}:
            cleaned.append(keyword)
    return cleaned


def _check_floors(floors: dict[str, str], categories: list[str], priorities: list[str] | None) -> None:
    for category, priority in floors.items():
        if category not in categories:
            raise ValueError(f"Catégorie inconnue dans les priorités minimales : {category}")
        if not priorities or priority not in priorities:
            raise ValueError(f"Priorité inconnue dans les priorités minimales : {priority}")


class Ticket(BaseModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=MAX_TICKET_CHARS)
    vip: bool = False  # client prioritaire : monte la priorité d'un cran
    age_days: int | None = Field(default=None, ge=0, le=36500)  # ancienneté du ticket, en jours


class TriageRequest(BaseModel):
    tickets: list[Ticket] = Field(min_length=1, max_length=MAX_TICKETS_PER_REQUEST)
    categories: list[str] = Field(min_length=2, max_length=MAX_LABELS)
    priorities: list[str] | None = Field(default=None, min_length=2, max_length=MAX_LABELS)
    urgent_keywords: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)
    floors: dict[str, str] = Field(default_factory=dict, max_length=MAX_LABELS)

    @field_validator("categories", "priorities")
    @classmethod
    def clean(cls, labels):
        return None if labels is None else _clean_labels(labels)

    @field_validator("urgent_keywords")
    @classmethod
    def clean_keywords(cls, keywords):
        return _clean_keywords(keywords)

    @model_validator(mode="after")
    def floors_are_consistent(self):
        _check_floors(self.floors, self.categories, self.priorities)
        return self


class TriageResult(BaseModel):
    id: str | None
    text: str
    category: str
    category_confidence: float
    priority: str | None = None
    priority_reasons: list[str] = Field(default_factory=list)


class TriageResponse(BaseModel):
    results: list[TriageResult]


class LabelSet(BaseModel):
    categories: list[str] = Field(min_length=2, max_length=MAX_LABELS)
    # Convention : la première priorité est la plus urgente, la dernière la moins urgente
    priorities: list[str] = Field(default_factory=list, max_length=MAX_LABELS)
    urgent_keywords: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)
    floors: dict[str, str] = Field(default_factory=dict, max_length=MAX_LABELS)

    @field_validator("categories", "priorities")
    @classmethod
    def clean(cls, labels):
        return _clean_labels(labels)

    @field_validator("urgent_keywords")
    @classmethod
    def clean_keywords(cls, keywords):
        return _clean_keywords(keywords)

    @model_validator(mode="after")
    def priorities_are_consistent(self):
        if len(self.priorities) == 1:
            raise ValueError("Indiquez au moins deux priorités, ou aucune.")
        _check_floors(self.floors, self.categories, self.priorities)
        return self
