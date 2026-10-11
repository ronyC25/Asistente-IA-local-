"""Definiciones (JSON Schema) de las herramientas disponibles."""
from __future__ import annotations

from ..tools import calendar, email_tool, messaging, notify, reminders, tasks
from .registry import READ, WRITE


def _describe_crear_tarea(a: dict) -> str:
    parts = [f"Crear la tarea «{a.get('titulo', '?')}»"]
    if a.get("prioridad"):
        parts.append(f"prioridad {a['prioridad']}")
    if a.get("fecha_limite"):
        parts.append(f"con fecha limite {a['fecha_limite']}")
    if a.get("descripcion"):
        parts.append(f"(descripcion: {a['descripcion']})")
    return ", ".join(parts)


def _describe_completar(a: dict) -> str:
    ref = a.get("id") if a.get("id") is not None else a.get("titulo")
    return f"Marcar como completada la tarea {ref!r}"


def _describe_editar(a: dict) -> str:
    ref = a.get("id") if a.get("id") is not None else a.get("titulo")
    cambios = {
        k: v
        for k, v in a.items()
        if k not in ("id", "titulo") and v is not None
    }
    return f"Editar la tarea {ref!r} -> {cambios}"


def _describe_eliminar(a: dict) -> str:
    ref = a.get("id") if a.get("id") is not None else a.get("titulo")
    return f"Eliminar la tarea {ref!r}"


def _describe_crear_recordatorio(a: dict) -> str:
    canal = a.get("canal", "windows")
    return (
        f"Crear el recordatorio «{a.get('texto', '?')}» para {a.get('cuando', '?')} "
        f"(aviso por {canal})"
    )


def _describe_cancelar_recordatorio(a: dict) -> str:
    return f"Cancelar el recordatorio id {a.get('id')}"


def _describe_enviar_telegram(a: dict) -> str:
    cid = str(a.get("chat_id") or "").strip()
    if cid and cid.lstrip("-").isdigit():
        destino = cid
    else:
        destino = "chat configurado"
    return f"Enviar por Telegram a {destino}: «{a.get('mensaje', '?')}»"


def _describe_enviar_email(a: dict) -> str:
    return (
        f"Enviar un correo a {a.get('destinatario', '?')} "
        f"con asunto «{a.get('asunto', '(sin asunto)')}»"
    )


def _describe_crear_evento(a: dict) -> str:
    partes = [f"Crear el evento «{a.get('titulo', '?')}» para {a.get('inicio', '?')}"]
    if a.get("fin"):
        partes.append(f"hasta {a['fin']}")
    if a.get("lugar"):
        partes.append(f"en {a['lugar']}")
    return ", ".join(partes)


def _describe_editar_evento(a: dict) -> str:
    cambios = {k: v for k, v in a.items() if k != "id" and v is not None}
    return f"Editar el evento id {a.get('id')} -> {cambios}"


def _describe_cancelar_evento(a: dict) -> str:
    return f"Cancelar el evento id {a.get('id')}"


def _describe_exportar_ics(a: dict) -> str:
    rango = ""
    if a.get("desde") or a.get("hasta"):
        rango = f" (desde {a.get('desde', '...')} hasta {a.get('hasta', '...')})"
    return f"Exportar los eventos a un archivo .ics{rango}"


def build_tools() -> list[dict]:
    return [
        {
            "name": "crear_tarea",
            "description": (
                "Crea una nueva tarea. Usa fecha_limite en formato ISO "
                "(YYYY-MM-DD o YYYY-MM-DDTHH:MM)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Titulo breve de la tarea"},
                    "descripcion": {"type": "string", "description": "Detalle opcional"},
                    "prioridad": {
                        "type": "string",
                        "enum": ["alta", "media", "baja"],
                        "description": "Prioridad de la tarea (por defecto media)",
                    },
                    "fecha_limite": {
                        "type": "string",
                        "description": "Fecha limite en formato ISO",
                    },
                },
                "required": ["titulo"],
            },
            "func": tasks.crear_tarea,
            "kind": WRITE,
            "describe": _describe_crear_tarea,
        },
        {
            "name": "listar_tareas",
            "description": "Lista las tareas guardadas con filtros opcionales.",
            "parameters": {
                "type": "object",
                "properties": {
                    "estado": {
                        "type": "string",
                        "enum": ["pendientes", "completadas", "todas"],
                        "description": "Que tareas listar (por defecto pendientes)",
                    },
                    "prioridad": {
                        "type": "string",
                        "enum": ["alta", "media", "baja"],
                    },
                    "vencen_hoy": {
                        "type": "boolean",
                        "description": "Solo tareas que vencen hoy",
                    },
                    "limite": {"type": "integer", "description": "Maximo de resultados"},
                },
            },
            "func": tasks.listar_tareas,
            "kind": READ,
        },
        {
            "name": "completar_tarea",
            "description": "Marca una tarea como completada por id o por titulo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Id de la tarea"},
                    "titulo": {"type": "string", "description": "Texto parcial del titulo"},
                },
            },
            "func": tasks.completar_tarea,
            "kind": WRITE,
            "describe": _describe_completar,
        },
        {
            "name": "editar_tarea",
            "description": "Edita los campos de una tarea existente (por id o titulo).",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "titulo": {"type": "string", "description": "Texto parcial para ubicar la tarea"},
                    "nuevo_titulo": {"type": "string"},
                    "descripcion": {"type": "string"},
                    "prioridad": {"type": "string", "enum": ["alta", "media", "baja"]},
                    "fecha_limite": {"type": "string"},
                    "estado": {"type": "string", "enum": ["pendiente", "completada"]},
                },
            },
            "func": tasks.editar_tarea,
            "kind": WRITE,
            "describe": _describe_editar,
        },
        {
            "name": "eliminar_tarea",
            "description": "Elimina definitivamente una tarea por id o titulo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "titulo": {"type": "string"},
                },
            },
            "func": tasks.eliminar_tarea,
            "kind": WRITE,
            "describe": _describe_eliminar,
        },
        {
            "name": "fecha_hora_actual",
            "description": (
                "Devuelve la fecha y hora actual. Usala para resolver "
                "expresiones relativas como 'manana' o 'el martes'."
            ),
            "parameters": {"type": "object", "properties": {}},
            "func": tasks.fecha_hora_actual,
            "kind": READ,
        },
        {
            "name": "crear_recordatorio",
            "description": (
                "Programa un recordatorio que se avisara en la fecha/hora indicada. "
                "Usa 'cuando' en formato ISO (YYYY-MM-DD HH:MM) y en el futuro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Que debe recordarse",
                    },
                    "cuando": {
                        "type": "string",
                        "description": "Fecha y hora del aviso en formato ISO",
                    },
                    "canal": {
                        "type": "string",
                        "enum": ["windows", "telegram"],
                        "description": "Como enviar el aviso (por defecto windows)",
                    },
                },
                "required": ["texto", "cuando"],
            },
            "func": reminders.crear_recordatorio,
            "kind": WRITE,
            "describe": _describe_crear_recordatorio,
        },
        {
            "name": "listar_recordatorios",
            "description": "Lista los recordatorios guardados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "estado": {
                        "type": "string",
                        "enum": ["pendientes", "enviados", "cancelados", "todos"],
                        "description": "Que recordatorios listar (por defecto pendientes)",
                    },
                    "limite": {"type": "integer"},
                },
            },
            "func": reminders.listar_recordatorios,
            "kind": READ,
        },
        {
            "name": "cancelar_recordatorio",
            "description": "Cancela un recordatorio pendiente por su id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Id del recordatorio"},
                },
                "required": ["id"],
            },
            "func": reminders.cancelar_recordatorio,
            "kind": WRITE,
            "describe": _describe_cancelar_recordatorio,
        },
        {
            "name": "enviar_notificacion_windows",
            "description": "Muestra una notificacion inmediata en Windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "mensaje": {"type": "string"},
                },
                "required": ["titulo", "mensaje"],
            },
            "func": notify.enviar_notificacion_windows,
            "kind": READ,
        },
        {
            "name": "enviar_telegram",
            "description": (
                "Envia un mensaje por Telegram al chat configurado (o a un chat_id "
                "concreto)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mensaje": {"type": "string", "description": "Texto a enviar"},
                    "chat_id": {
                        "type": "string",
                        "description": (
                            "NO lo rellenes. Dejalo vacio para usar el chat "
                            "configurado; solo indica un id numerico si el usuario "
                            "pide enviar a un chat concreto."
                        ),
                    },
                },
                "required": ["mensaje"],
            },
            "func": messaging.enviar_telegram,
            "kind": WRITE,
            "describe": _describe_enviar_telegram,
        },
        {
            "name": "leer_email",
            "description": "Lee los correos mas recientes del buzon IMAP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "carpeta": {"type": "string", "description": "Por defecto INBOX"},
                    "limite": {"type": "integer", "description": "Cuantos correos (por defecto 5)"},
                    "no_leidos": {
                        "type": "boolean",
                        "description": "Si es true, solo correos no leidos",
                    },
                },
            },
            "func": email_tool.leer_email,
            "kind": READ,
        },
        {
            "name": "enviar_email",
            "description": "Envia un correo electronico por SMTP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destinatario": {"type": "string"},
                    "asunto": {"type": "string"},
                    "cuerpo": {"type": "string"},
                },
                "required": ["destinatario", "asunto", "cuerpo"],
            },
            "func": email_tool.enviar_email,
            "kind": WRITE,
            "describe": _describe_enviar_email,
        },
        {
            "name": "crear_evento",
            "description": (
                "Agenda un evento en el calendario local. Usa 'inicio' (y opcional "
                "'fin') en formato ISO. Para todo el dia, pasa todo_el_dia=true y una "
                "fecha sin hora."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "inicio": {"type": "string", "description": "Fecha/hora de inicio ISO"},
                    "fin": {"type": "string", "description": "Fecha/hora de fin ISO (opcional)"},
                    "todo_el_dia": {"type": "boolean"},
                    "lugar": {"type": "string"},
                    "notas": {"type": "string"},
                },
                "required": ["titulo", "inicio"],
            },
            "func": calendar.crear_evento,
            "kind": WRITE,
            "describe": _describe_crear_evento,
        },
        {
            "name": "listar_eventos",
            "description": (
                "Lista los eventos del calendario. Por defecto muestra los proximos "
                "desde ahora."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha ISO inicial (opcional)"},
                    "hasta": {"type": "string", "description": "Fecha ISO final (opcional)"},
                    "incluir_cancelados": {"type": "boolean"},
                    "limite": {"type": "integer"},
                },
            },
            "func": calendar.listar_eventos,
            "kind": READ,
        },
        {
            "name": "editar_evento",
            "description": "Edita un evento existente por su id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "titulo": {"type": "string"},
                    "inicio": {"type": "string"},
                    "fin": {"type": "string"},
                    "todo_el_dia": {"type": "boolean"},
                    "lugar": {"type": "string"},
                    "notas": {"type": "string"},
                    "estado": {"type": "string", "enum": ["activo", "cancelado"]},
                },
                "required": ["id"],
            },
            "func": calendar.editar_evento,
            "kind": WRITE,
            "describe": _describe_editar_evento,
        },
        {
            "name": "cancelar_evento",
            "description": "Cancela un evento por su id.",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
            "func": calendar.cancelar_evento,
            "kind": WRITE,
            "describe": _describe_cancelar_evento,
        },
        {
            "name": "exportar_ics",
            "description": (
                "Exporta los eventos a un archivo .ics (compatible con Google "
                "Calendar, Outlook, etc.). Si no indicas rango, exporta TODOS los "
                "eventos; no pidas fechas al usuario, exporta directamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "desde": {"type": "string"},
                    "hasta": {"type": "string"},
                    "ruta": {"type": "string", "description": "Ruta de destino opcional"},
                },
            },
            "func": calendar.exportar_ics,
            "kind": WRITE,
            "describe": _describe_exportar_ics,
        },
    ]
