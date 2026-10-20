"""Limpieza de formato Markdown de las respuestas del asistente.

El modelo a veces responde con **negritas**, `codigo`, # titulos, etc. Eso se ve
mal en los mensajes y, en voz, la sintesis lee los asteriscos. Esta funcion deja
texto plano.
"""
from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"```[a-zA-Z0-9]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_STRIKE = re.compile(r"~~(.+?)~~")
_HEADER = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BULLET = re.compile(r"^\s*[*+-]\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|__)(?=\S)(.+?)(?<=\S)\1")
_THINK = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think\b[^>]*>.*", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Quita bloques de razonamiento ``<think>...</think>`` que algunos modelos
    filtran en el contenido (incluso con ``think=False``)."""
    t = _THINK.sub("", text or "")
    # Bloque sin cerrar (respuesta truncada): descartamos el razonamiento.
    t = _THINK_OPEN.sub("", t)
    return t.strip()


def strip_markdown(text: str) -> str:
    """Quita el formato Markdown y deja texto plano."""
    t = text or ""
    t = _CODE_FENCE.sub(r"\1", t)
    t = _INLINE_CODE.sub(r"\1", t)
    t = _LINK.sub(r"\1", t)
    t = _STRIKE.sub(r"\1", t)
    t = _HEADER.sub("", t)
    t = _BULLET.sub("• ", t)
    t = _EMPHASIS.sub(r"\2", t)
    # Restos de asteriscos/backticks sueltos (p. ej. listas o enfasis mal formado).
    t = t.replace("*", "").replace("`", "")
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()
