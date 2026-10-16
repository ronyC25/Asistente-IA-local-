"""Logica de confirmacion de acciones pendientes (sin dependencias de red)."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_YES = {
    "si",
    "s",
    "claro",
    "confirmo",
    "confirmar",
    "confirmado",
    "confirmalo",
    "ok",
    "okay",
    "dale",
    "adelante",
    "hazlo",
    "hacelo",
    "correcto",
    "afirmativo",
    "yes",
    "y",
    "vale",
    "perfecto",
    "de acuerdo",
    "por supuesto",
    "obvio",
    "efectivamente",
}

_NO = {
    "no",
    "n",
    "cancelar",
    "cancela",
    "cancela lo",
    "cancelo",
    "negativo",
    "no gracias",
    "espera",
    "para",
    "detente",
    "mejor no",
    "nunca",
    "olvidalo",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# Verbos que indican que el usuario pide una ACCION (no solo una consulta).
_ACTION_VERBS = {
    "manda",
    "mandame",
    "envia",
    "enviame",
    "crea",
    "creame",
    "agenda",
    "agendame",
    "programa",
    "programame",
    "recuerdame",
    "recordarme",
    "elimina",
    "borra",
    "edita",
    "cambia",
    "cancela",
    "completa",
    "marca",
    "responde",
    "escribe",
    "anade",
    "agrega",
    "exporta",
    "avisame",
    "avisa",
}


def looks_like_action(text: str) -> bool:
    """Heuristica: True si el mensaje parece pedir una accion de escritura."""
    t = _norm(text)
    if not t:
        return False
    palabras = set(t.split())
    return bool(palabras & _ACTION_VERBS)


# Verbos/sustantivos que indican una CONSULTA (lectura de datos).
_QUERY_WORDS = {
    "revisa",
    "revisar",
    "revisame",
    "revisen",
    "lista",
    "listar",
    "listame",
    "muestra",
    "muestrame",
    "mostrar",
    "dime",
    "consulta",
    "consultar",
    "cuantas",
    "cuantos",
    "cuales",
    "cual",
    "tengo",
    "hay",
    "ver",
    "veamos",
    "pendientes",
    "agenda",
    "calendario",
    "eventos",
    "recordatorios",
    "tareas",
    "correos",
    "correo",
    "emails",
    "hoy",
    "manana",
}


def looks_like_query(text: str) -> bool:
    """Heuristica: True si el mensaje parece pedir una consulta (lectura)."""
    t = _norm(text)
    if not t:
        return False
    palabras = set(t.split())
    return bool(palabras & _QUERY_WORDS)


_HISTORIAL_WORDS = {
    "lista",
    "listado",
    "listame",
    "todos",
    "todas",
    "historial",
    "completos",
    "completas",
    "cuales",
}
_PENDIENTE_WORDS = {
    "pendiente",
    "pendientes",
    "proximo",
    "proximos",
    "vencen",
    "vencido",
    "vencidos",
    "futuro",
    "futuros",
    "activo",
    "activos",
}


def quiere_historial_recordatorios(text: str) -> bool:
    """True si el usuario pide el historial de recordatorios (no solo pendientes)."""
    t = _norm(text)
    if not t:
        return False
    if "cancelad" in t:  # pide cancelados explicitamente
        return False
    palabras = set(t.split())
    if palabras & _PENDIENTE_WORDS:
        return False
    return bool(palabras & _HISTORIAL_WORDS)


_WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def periodo_de_texto(text: str) -> tuple[str, int | None] | None:
    """Detecta una expresion de rango relativo y devuelve (periodo, dias) o None.

    Sirve para resolver fechas de forma determinista (sin que el modelo calcule).
    """
    t = _norm(text)
    if not t:
        return None
    if "pasado manana" in t:
        return ("pasado_manana", None)
    if "fin de semana" in t or "finde" in t:
        return ("fin_de_semana", None)
    if any(
        frase in t
        for frase in (
            "semana que viene",
            "proxima semana",
            "semana siguiente",
            "la otra semana",
        )
    ):
        return ("semana_que_viene", None)
    if "esta semana" in t:
        return ("esta_semana", None)
    if "este mes" in t or "mes en curso" in t:
        return ("este_mes", None)
    m = re.search(r"(?:proximos|proximas|siguientes)\s+(\d+)\s+dias?", t)
    if m:
        return ("proximos_dias", int(m.group(1)))
    if "hoy" in t:
        return ("hoy", None)
    if "manana" in t:
        return ("manana", None)
    for wd in _WEEKDAYS:
        if re.search(rf"\b{wd}\b", t):
            return (wd, None)
    return None


def classify_confirmation(text: str) -> bool | None:
    """Devuelve True (confirmar), False (cancelar) o None (ambiguo)."""
    t = _norm(text)
    if not t:
        return None

    def matches(word_set: set[str]) -> bool:
        if t in word_set:
            return True
        first = t.split()[0]
        return first in word_set

    if matches(_NO):
        return False
    if matches(_YES):
        return True
    return None


def build_proposal(parsed: list[tuple[str, dict]], registry: Any) -> str:
    lines: list[str] = []
    for name, args in parsed:
        tool = registry.get(name)
        if tool is not None and tool.describe is not None:
            lines.append("• " + tool.describe(args or {}))
        else:
            params = ", ".join(f"{k}={v}" for k, v in (args or {}).items())
            lines.append(f"• {name}({params})")
    body = "\n".join(lines)
    return (
        "Voy a realizar la siguiente accion:\n"
        f"{body}\n\n"
        "¿Confirmas? (si/no)"
    )
