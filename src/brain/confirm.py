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
    "nota",
    "notas",
    "apunte",
    "apuntes",
    "notificacion",
    "notificaciones",
    "aviso",
    "avisos",
    "alarma",
    "alarmas",
    "checklist",
    "checklists",
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


# Dominio de datos -> palabras clave (sustantivos, sin ambiguedad de verbos).
_DOMINIO_KEYWORDS = (
    (
        "recordatorios",
        (
            "notificacion",
            "notificaciones",
            "recordatorio",
            "recordatorios",
            "aviso",
            "avisos",
            "alarma",
            "alarmas",
        ),
    ),
    ("tareas", ("tarea", "tareas")),
    ("notas", ("nota", "notas", "apunte", "apuntes")),
    (
        "listas",
        ("checklist", "checklists", "lista de la compra", "lista de compras"),
    ),
    (
        "eventos",
        ("evento", "eventos", "calendario", "agenda", "cita", "citas", "reunion", "reuniones"),
    ),
    ("email", ("correo", "correos", "email", "emails")),
)


def dominio_lectura(text: str) -> str | None:
    """Detecta el dominio de datos de una consulta (p. ej. 'notificaciones').

    Devuelve una clave de dominio ('tareas', 'recordatorios', 'notas', 'listas',
    'eventos', 'email') o None. 'notificaciones' cuenta como recordatorios.
    """
    t = _norm(text)
    if not t:
        return None
    palabras = set(t.split())
    for dominio, claves in _DOMINIO_KEYWORDS:
        for k in claves:
            if (" " in k and k in t) or (" " not in k and k in palabras):
                return dominio
    return None


def orden_de_texto(text: str) -> str | None:
    """Detecta 'lo mas antiguo' o 'lo mas reciente' (None si no aplica)."""
    t = _norm(text)
    if not t:
        return None
    palabras = set(t.split())
    if palabras & {
        "antiguo",
        "antigua",
        "antiguos",
        "antiguas",
        "viejo",
        "vieja",
        "viejos",
        "viejas",
    }:
        return "antiguas"
    if palabras & {
        "reciente",
        "recientes",
        "ultimo",
        "ultima",
        "ultimos",
        "ultimas",
    }:
        return "recientes"
    return None


def quiere_proximo(text: str) -> bool:
    """True si piden el proximo/siguiente (p. ej. 'el evento mas proximo')."""
    palabras = set(_norm(text).split())
    return bool(
        palabras
        & {"proximo", "proxima", "proximos", "proximas", "siguiente", "siguientes"}
    )


def pregunta_cuanto_falta(text: str) -> bool:
    """True si preguntan cuanto falta/queda para algo."""
    t = _norm(text)
    return (
        "cuanto falta" in t
        or "cuanto queda" in t
        or "cuanto tiempo" in t
        or "falta para" in t
    )


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
