"""Priorité d'un ticket par règles explicites (et non par l'IA).

Une règle est prévisible et explicable : chaque priorité proposée vient avec ses raisons.
Convention : dans la liste des priorités, la première est la plus urgente et la dernière la moins urgente.
"""
import re
import unicodedata

AGE_ESCALATION_DAYS = 7  # un ticket qui attend depuis au moins ce nombre de jours monte d'un cran

# Mots qui annulent un signal s'ils le précèdent de près (« pas urgent », « mon compte n'est pas bloqué »)
NEGATORS = {"pas", "non", "sans", "aucun", "aucune", "jamais", "ni", "not", "no", "never", "without"}
NEGATION_WINDOW = 3

# Signaux d'urgence (texte normalisé : minuscules, sans accents). Les racines acceptent les terminaisons.
URGENT_PATTERNS = [
    r"urgen\w*", r"immediat\w*", r"asap", r"dans les plus brefs delais",
    r"bloqu\w*", r"hors service", r"plus rien ne (?:marche|fonctionne)",
    r"ne (?:fonctionne|marche) (?:plus|pas)", r"(?:ne )?(?:marche|fonctionne) plus",
    r"perd\w* (?:des |de l |de la |mes |nos |tout )?(?:ventes|clients|argent|donnees|chiffre)",
    r"perte de (?:ventes|clients|argent|donnees|chiffre)",
    r"fraude\w*", r"frauduleu\w*", r"pirat\w*", r"donnees personnelles", r"fuite de donnees",
    r"avocat\w*", r"mise en demeure", r"tribunal", r"justice", r"plainte\w*", r"porter plainte",
    r"resili\w*", r"inacceptable", r"scandal\w*",
    r"double prelevement", r"prelev\w* (?:deux|2) fois", r"debit\w* (?:deux|2) fois",
    r"depuis (?:plus de |pres de )?(?:\d+|deux|trois|quatre|cinq|six|plusieurs) (?:semaines?|mois)",
    r"not working", r"is down", r"blocked", r"immediately", r"lawyer", r"legal action", r"data breach", r"cancel\w*",
]

# Signaux de faible priorité : comptent seulement s'il n'y a aucun signal d'urgence
LOW_PATTERNS = [
    r"sans urgence", r"pour information", r"pour info", r"a titre informatif", r"suggestion\w*",
    r"idee d amelioration", r"simple question", r"quand vous (?:aurez le temps|pourrez)",
    r"curiosite", r"felicitation\w*", r"no rush", r"for your information", r"just a question",
]

_URGENT = [re.compile(rf"(?<!\w){p}") for p in URGENT_PATTERNS]
_LOW = [re.compile(rf"(?<!\w){p}") for p in LOW_PATTERNS]


def _fold(text: str) -> tuple[str, list[int]]:
    """Minuscules, sans accents, ponctuation remplacée par un seul espace.

    Retourne aussi, pour chaque caractère du résultat, sa position dans le texte d'origine :
    les raisons affichées peuvent ainsi citer le texte réel du ticket (avec ses accents).
    """
    out: list[str] = []
    origin: list[int] = []
    last_space = True
    for i, char in enumerate(text):
        for c in unicodedata.normalize("NFKD", char.casefold()):
            if unicodedata.combining(c):
                continue
            if c.isalnum() or c == "_":
                out.append(c)
                origin.append(i)
                last_space = False
            elif not last_space:
                out.append(" ")
                origin.append(i)
                last_space = True
    if out and out[-1] == " ":
        out.pop()
        origin.pop()
    return "".join(out), origin


def normalize(text: str) -> str:
    return _fold(text)[0]


def _negated(text: str, start: int) -> bool:
    previous = text[:start].split()[-NEGATION_WINDOW:]
    return any(word in NEGATORS for word in previous)


def _find(patterns, folded: str, origin: list[int], original: str) -> list[tuple[str, bool]]:
    """Signaux trouvés : (texte d'origine, annulé par une négation)."""
    found = []
    for pattern in patterns:
        for match in pattern.finditer(folded):
            quote = original[origin[match.start()]: origin[match.end() - 1] + 1]
            found.append((quote, _negated(folded, match.start())))
    return found


def _unique(words: list[str]) -> list[str]:
    seen, result = set(), []
    for word in words:
        if word.casefold() not in seen:
            seen.add(word.casefold())
            result.append(word)
    return result


def default_index(count: int) -> int:
    """Position de la priorité « normale » quand rien de particulier n'est repéré."""
    return (count - 1) // 2 if count >= 3 else count - 1


def compute_priority(
    text: str,
    priorities: list[str],
    category: str | None = None,
    extra_keywords: list[str] | None = None,
    floors: dict[str, str] | None = None,
    vip: bool = False,
    age_days: int | None = None,
) -> tuple[str, list[str]]:
    """Retourne (priorité, raisons). `priorities` va de la plus urgente à la moins urgente."""
    count = len(priorities)
    folded, origin = _fold(text)
    reasons: list[str] = []

    custom = [re.compile(rf"(?<!\w){re.escape(normalize(k))}\w*") for k in (extra_keywords or []) if normalize(k)]
    urgent = _find(_URGENT + custom, folded, origin, text)
    real_urgent = _unique([w for w, neg in urgent if not neg])
    negated_urgent = _unique([w for w, neg in urgent if neg])
    low = _unique([w for w, neg in _find(_LOW, folded, origin, text) if not neg])

    if real_urgent:
        index = 0
        reasons.append("mot-clé d'urgence : " + ", ".join(real_urgent[:3]))
    elif low or negated_urgent:
        index = count - 1
        reasons.append("signal de faible urgence : " + ", ".join((low or negated_urgent)[:3]))
    else:
        index = default_index(count)
        reasons.append("aucun signal particulier")

    if vip:
        index = max(0, index - 1)
        reasons.append("client VIP (+1 cran)")
    if age_days is not None and age_days >= AGE_ESCALATION_DAYS:
        index = max(0, index - 1)
        reasons.append(f"ticket en attente depuis {age_days} jours (+1 cran)")

    floor = (floors or {}).get(category or "")
    if floor in priorities and priorities.index(floor) < index:
        index = priorities.index(floor)
        reasons.append(f"minimum pour la catégorie « {category} »")

    return priorities[index], reasons
