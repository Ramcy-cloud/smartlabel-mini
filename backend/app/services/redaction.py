"""Masquage des données personnelles évidentes avant d'envoyer un texte à un service externe.

Limite : ce masquage repère des formats (email, téléphone, IBAN, carte, lien), pas des noms ou des adresses.
Il réduit l'exposition, il ne rend pas un texte anonyme.
"""
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
_CARD = re.compile(r"(?<!\w)(?:\d[ -]?){13,19}(?!\w)")
_PHONE = re.compile(r"(?<!\w)(?:\+|00)?\d(?:[\s.\-()]?\d){8,13}(?!\w)")

# L'ordre compte : une carte (16 chiffres) ne doit pas être prise pour un téléphone
_RULES = [(_EMAIL, "[email]"), (_URL, "[lien]"), (_IBAN, "[iban]"), (_CARD, "[carte]"), (_PHONE, "[téléphone]")]


def redact(text: str) -> str:
    for pattern, placeholder in _RULES:
        text = pattern.sub(placeholder, text)
    return text
