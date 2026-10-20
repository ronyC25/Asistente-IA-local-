"""Deteccion de llamadas a herramientas escritas como TEXTO.

Algunos modelos (p. ej. qwen3) a veces devuelven la llamada dentro del contenido
en vez de en ``tool_calls``::

    {"name": "listar_eventos", "arguments": {"periodo": "esta_semana"}}

Estas utilidades permiten recuperar esa intencion y convertirla en una llamada
real, para no mostrar/hablar JSON crudo.
"""
from __future__ import annotations

import json
import re

_TOOL_TAGS = re.compile(
    r"<tool_call>|</tool_call>|<\|?tool_call\|?>|<\|?python_tag\|?>", re.IGNORECASE
)
_FUNC_CALL = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*(\{.*?\})\s*\)", re.DOTALL)
_JSON_START = re.compile(r"\{")


def _objetos_json(texto: str):
    """Itera los objetos JSON presentes en ``texto`` (ignora basura alrededor)."""
    dec = json.JSONDecoder()
    i = 0
    while i < len(texto):
        match = _JSON_START.search(texto, i)
        if not match:
            return
        try:
            obj, end = dec.raw_decode(texto, match.start())
        except json.JSONDecodeError:
            i = match.start() + 1
            continue
        yield obj
        i = max(end, match.start() + 1)


def _args_de(valor):
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            return None
    return valor if isinstance(valor, dict) else None


def extraer_llamadas(
    texto: str, nombres: set[str] | None = None
) -> list[tuple[str, dict]]:
    """Devuelve las llamadas ``(nombre, argumentos)`` escritas como texto.

    ``nombres`` limita a herramientas conocidas (evita falsos positivos con JSON
    que no sea una llamada).
    """
    texto = texto or ""
    validos = nombres or set()
    out: list[tuple[str, dict]] = []
    for obj in _objetos_json(texto):
        if not isinstance(obj, dict):
            continue
        nombre = obj.get("name") or obj.get("tool") or obj.get("function")
        if isinstance(nombre, dict):
            nombre = nombre.get("name")
        if not isinstance(nombre, str) or (validos and nombre not in validos):
            continue
        args = _args_de(
            obj.get("arguments", obj.get("parameters", obj.get("args", {})))
        )
        if args is not None:
            out.append((nombre, args))
    if out:
        return out
    for match in _FUNC_CALL.finditer(texto):
        nombre = match.group(1)
        if validos and nombre not in validos:
            continue
        try:
            args = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
        if isinstance(args, dict):
            out.append((nombre, args))
    return out


def parece_llamada(texto: str, nombres: set[str] | None = None) -> bool:
    """True si el texto contiene una llamada a herramienta (JSON, tags o ``f(...)``)."""
    t = texto or ""
    if _TOOL_TAGS.search(t):
        return True
    return bool(extraer_llamadas(t, nombres))
