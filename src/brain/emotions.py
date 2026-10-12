"""Parseo de etiquetas de emocion en las respuestas del asistente."""
from __future__ import annotations

import re

# Emociones validas (se mapean a expresiones del avatar en el frontend).
EMOCIONES = {
    "joy",
    "happy",
    "sad",
    "angry",
    "surprised",
    "relaxed",
    "neutral",
    "excited",
    "shy",
    "smug",
    "confused",
    "thinking",
}

_PATTERN = re.compile(r"\[([a-zA-Z]+)\]")


def strip_emotions(text: str) -> tuple[str, list[str]]:
    """Extrae las etiquetas [emocion] y devuelve (texto_limpio, emociones).

    Solo reconoce emociones de la lista EMOCIONES; cualquier otro [texto]
    se deja intacto.
    """
    emociones: list[str] = []

    def _repl(match: re.Match) -> str:
        palabra = match.group(1).lower()
        if palabra in EMOCIONES:
            emociones.append(palabra)
            return ""
        return match.group(0)

    limpio = _PATTERN.sub(_repl, text or "")
    limpio = re.sub(r"[ \t]{2,}", " ", limpio)
    limpio = re.sub(r"\s+([,.!?;:])", r"\1", limpio)
    return limpio.strip(), emociones
