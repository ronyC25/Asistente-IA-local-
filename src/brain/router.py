"""Seleccion determinista de grupos de herramientas por turno.

El prompt completo (27 tools) ocupa ~4.6k tokens. Enviar solo el grupo del
dominio baja el prompt a ~1-2k y deja sitio para memoria e historial.
"""
from __future__ import annotations

import re
import unicodedata

from .confirm import (
    dominio_lectura,
    es_busqueda,
    intencion_temporizador,
    looks_like_action,
    looks_like_query,
    pregunta_capacidades,
)

GRUPOS: dict[str, set[str]] = {
    "core": {"fecha_hora_actual"},
    "busqueda": {"buscar_todo", "listar_etiquetas"},
    "tareas": {
        "crear_tarea",
        "listar_tareas",
        "editar_tarea",
        "completar_tarea",
        "eliminar_tarea",
    },
    "eventos": {
        "crear_evento",
        "listar_eventos",
        "editar_evento",
        "cancelar_evento",
        "exportar_ics",
        "sincronizar_calendario",
    },
    "recordatorios": {
        "crear_recordatorio",
        "listar_recordatorios",
        "cancelar_recordatorio",
    },
    "notas": {"consultar_notas", "gestionar_notas"},
    "listas": {"consultar_listas", "gestionar_listas"},
    "temporizadores": {"consultar_temporizador", "gestionar_temporizador"},
    "mensajeria": {"enviar_telegram", "enviar_notificacion_windows"},
    "email": {"leer_email", "enviar_email"},
}

_DOMINIO_A_GRUPO = {
    "tareas": "tareas",
    "eventos": "eventos",
    "recordatorios": "recordatorios",
    "notas": "notas",
    "listas": "listas",
    "temporizadores": "temporizadores",
    "email": "email",
    "busqueda": "busqueda",
}

_MENSAJERIA = (
    "telegram",
    "whatsapp",
    "mensaje",
    "mensajeria",
    "notificame",
)
_EMAIL = ("correo", "correos", "email", "emails", "gmail")
_BUSQUEDA = ("busca", "buscar", "buscame", "encuentra", "localiza", "etiqueta", "etiquetas")
_RECORDATORIO_VERBO = (
    "recuerdame",
    "recordarme",
    "avisame",
    "avisa",
    "alarma",
    "alarmas",
)
_ACCIONES_MENSAJERIA = (
    "manda",
    "mandame",
    "envia",
    "enviame",
    "notificame",
    "avisa",
    "avisame",
)
_EVENTO_EXTRA = ("cumpleanos", "cumple", "examen", "examenes", "entrega", "entregas")
_TAREA_EXTRA = ("subtarea", "subtareas", "pendiente", "pendientes")
_NOTA_EXTRA = ("apunta", "apuntar", "anota", "anotar")
_LISTA_EXTRA = ("checklist", "checklists", "compra", "compras")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def todos_los_grupos() -> set[str]:
    return set(GRUPOS)


def nombres(grupos: set[str] | None) -> set[str]:
    if not grupos:
        return set()
    out: set[str] = set()
    for grupo in grupos:
        out.update(GRUPOS.get(grupo, set()))
    return out


def grupos_para(user_text: str, session=None) -> set[str]:
    """Devuelve los grupos de tools relevantes para el mensaje.

    Si no hay ninguna senal clara pero el mensaje parece accion/consulta, usa
    todos los grupos (fallback); para saludos basta con ``core``.
    """
    t = _norm(user_text)
    previos = set(getattr(session, "grupos", set()) or set()) if session else set()
    pendiente = bool(getattr(session, "pending", None)) if session else False
    if not t:
        return {"core"} | (previos if pendiente else set())

    if pregunta_capacidades(user_text):
        return {"core"}

    grupos: set[str] = {"core"}

    intent = intencion_temporizador(user_text)
    if intent:
        grupos.add("temporizadores")

    dominio = dominio_lectura(user_text)
    if dominio:
        grupo = _DOMINIO_A_GRUPO.get(dominio)
        if grupo:
            grupos.add(grupo)

    palabras = set(t.split())
    if any(w in palabras or w in t for w in _MENSAJERIA):
        grupos.add("mensajeria")
    if any(w in palabras for w in _EMAIL):
        grupos.add("email")
    if es_busqueda(user_text) or any(w in palabras for w in _BUSQUEDA):
        grupos.add("busqueda")
    if any(w in palabras for w in _RECORDATORIO_VERBO):
        grupos.add("recordatorios")
    if any(w in palabras for w in _EVENTO_EXTRA):
        grupos.add("eventos")
    if any(w in palabras for w in _TAREA_EXTRA):
        grupos.add("tareas")
    if any(w in palabras for w in _NOTA_EXTRA):
        grupos.add("notas")
    if any(w in palabras for w in _LISTA_EXTRA):
        grupos.add("listas")

    # "manda una notificacion" es mensajeria; "que notificaciones tengo" es
    # una consulta de recordatorios.
    if (
        any(w in palabras for w in ("notificacion", "notificaciones"))
        and any(w in palabras for w in _ACCIONES_MENSAJERIA)
    ):
        grupos.add("mensajeria")
        grupos.discard("recordatorios")

    if len(grupos) == 1:
        if pendiente and previos:
            grupos |= previos
        elif looks_like_action(user_text) or looks_like_query(user_text):
            return todos_los_grupos()

    if pendiente and previos:
        grupos |= previos
    return grupos
