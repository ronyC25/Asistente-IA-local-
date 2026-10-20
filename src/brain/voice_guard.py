"""Filtro anti-eco para el modo voz/avatar.

El microfono puede captar la propia voz del asistente (sobre todo si el audio del
cliente aun se esta reproduciendo). Si el texto transcrito es practicamente el
mismo que acaba de decir el asistente, se ignora para no confundir al modelo.
"""
from __future__ import annotations

import re
import unicodedata

_STOP = {
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "unos",
    "unas",
    "de",
    "del",
    "al",
    "a",
    "en",
    "y",
    "o",
    "que",
    "por",
    "para",
    "con",
    "sin",
    "se",
    "su",
    "sus",
    "mi",
    "mis",
    "tu",
    "tus",
    "es",
    "son",
    "esta",
    "estan",
    "este",
    "esto",
    "lo",
    "le",
    "les",
    "ya",
    "muy",
    "hay",
    "como",
    "mas",
    "pero",
    "si",
    "no",
    "te",
    "me",
    "nos",
    "os",
}

# Si el usuario pregunta/ordena algo, NO es un eco aunque comparta palabras.
_EXCLUYE = {
    "cuando",
    "que",
    "como",
    "donde",
    "cuanto",
    "cuanta",
    "cuantos",
    "cuantas",
    "cual",
    "cuales",
    "quien",
    "quienes",
    "porque",
    "puedes",
    "puede",
    "podrias",
    "dime",
    "dame",
    "muestra",
    "listame",
    "lista",
    "busca",
    "encuentra",
    "agrega",
    "crea",
    "anade",
    "borra",
    "elimina",
    "cancela",
    "edita",
    "cambia",
    "marca",
    "completa",
    "envia",
    "manda",
    "recuerdame",
    "avisa",
    "pon",
    "inicia",
    "pausa",
    "reanuda",
    "deten",
    "para",
    "quiero",
    "necesito",
    "haz",
    "hazlo",
}


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parece_eco(texto: str, referencia: str | None) -> bool:
    """True si ``texto`` parece el propio audio del asistente (``referencia``)."""
    if not texto or not referencia:
        return False
    palabras = _norm(texto).split()
    if len(palabras) < 3:
        return False
    if set(palabras) & _EXCLUYE:
        return False
    ref = set(_norm(referencia).split())
    contenido = [w for w in palabras if w not in _STOP]
    if len(contenido) < 3:
        return False
    coinciden = sum(1 for w in contenido if w in ref)
    return coinciden / len(contenido) >= 0.8
