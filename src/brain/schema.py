"""Definiciones (JSON Schema) de las herramientas disponibles."""
from __future__ import annotations

from ..timeutil import PERIODOS
from ..tools import (
    calendar,
    email_tool,
    gcal,
    lists,
    messaging,
    notes,
    notify,
    reminders,
    search,
    tasks,
    timers,
)
from .registry import READ, WRITE


def _periodo_props() -> dict:
    """Propiedades comunes para filtrar por rango relativo (periodo + dias)."""
    return {
        "periodo": {
            "type": "string",
            "enum": list(PERIODOS),
            "description": (
                "Rango relativo de fechas. Prefierelo antes que calcular fechas: "
                "hoy, manana, pasado_manana, fin_de_semana, esta_semana, "
                "semana_que_viene, proximos_dias (usa 'dias'), este_mes, o un dia "
                "de la semana (lunes..domingo)."
            ),
        },
        "dias": {
            "type": "integer",
            "description": "Numero de dias cuando periodo=proximos_dias.",
        },
    }


def _etiquetas_prop() -> dict:
    """Propiedad 'etiquetas' (lista) para las herramientas de escritura."""
    return {
        "etiquetas": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Etiquetas/categorias (varias). Ej: ['trabajo', 'urgente']. "
                "Pasalo como lista de palabras."
            ),
        }
    }


def _etiqueta_filtro_prop() -> dict:
    """Propiedad 'etiqueta' (filtro exacto) para las herramientas de lectura."""
    return {
        "etiqueta": {
            "type": "string",
            "description": "Filtra por una etiqueta/categoria exacta.",
        }
    }


def _describe_crear_tarea(a: dict) -> str:
    parts = [f"Crear la tarea «{a.get('titulo', '?')}»"]
    if a.get("prioridad"):
        parts.append(f"prioridad {a['prioridad']}")
    if a.get("fecha_limite"):
        parts.append(f"con fecha limite {a['fecha_limite']}")
    if a.get("etiquetas"):
        parts.append(f"etiquetas {a['etiquetas']}")
    if a.get("padre_id"):
        parts.append(f"como subtarea de la tarea {a['padre_id']}")
    if a.get("descripcion"):
        parts.append(f"(descripcion: {a['descripcion']})")
    return ", ".join(parts)


def _tarea_ref(a: dict) -> str:
    if a.get("id") is not None:
        t = tasks.obtener_tarea(a["id"])
        return f"{a['id']} «{t['titulo']}»" if t else str(a["id"])
    return repr(a.get("titulo"))


def _recordatorio_ref(a: dict) -> str:
    if a.get("id") is not None:
        r = reminders.obtener_recordatorio(a["id"])
        return f"{a['id']} «{r['texto']}»" if r else str(a["id"])
    return "?"


def _evento_ref(a: dict) -> str:
    if a.get("id") is not None:
        e = calendar.obtener_evento(a["id"])
        return f"{a['id']} «{e['titulo']}»" if e else str(a["id"])
    if a.get("titulo"):
        return repr(a["titulo"])
    return "?"


def _describe_completar(a: dict) -> str:
    return f"Marcar como completada la tarea {_tarea_ref(a)}"


def _describe_editar(a: dict) -> str:
    cambios = {
        k: v
        for k, v in a.items()
        if k not in ("id", "titulo") and v is not None
    }
    return f"Editar la tarea {_tarea_ref(a)} -> {cambios}"


def _describe_eliminar(a: dict) -> str:
    return f"Eliminar la tarea {_tarea_ref(a)}"


def _describe_crear_recordatorio(a: dict) -> str:
    canal = a.get("canal", "windows")
    rec = a.get("recurrencia") or "ninguna"
    sufijo = "" if rec in ("ninguna", "") else f" (repite: {rec})"
    return (
        f"Crear el recordatorio «{a.get('texto', '?')}» para {a.get('cuando', '?')} "
        f"(aviso por {canal}){sufijo}"
    )


def _describe_gestionar_notas(a: dict) -> str:
    accion = str(a.get("accion", "?")).lower()
    ref = a.get("id") if a.get("id") is not None else a.get("titulo")
    if accion in ("crear", "anadir", "agregar", "nueva"):
        cuerpo = str(a.get("contenido") or "")[:60]
        return f"Crear una nota «{a.get('titulo') or cuerpo}»"
    if accion in ("editar", "actualizar", "modificar"):
        return f"Editar la nota {ref!r}"
    if accion in ("eliminar", "borrar", "borra"):
        return f"Eliminar la nota {ref!r}"
    return f"Notas: {accion}"


def _describe_gestionar_listas(a: dict) -> str:
    accion = str(a.get("accion", "?")).lower()
    ref = a.get("id") if a.get("id") is not None else a.get("nombre")
    items = a.get("items") or []
    if accion in ("crear", "nueva", "crea"):
        sufijo = f" con: {', '.join(str(i) for i in items)}" if items else ""
        return f"Crear la lista «{a.get('nombre', '?')}»{sufijo}"
    if accion in ("agregar", "anadir", "add"):
        if items:
            return f"Agregar a la lista {ref}: {', '.join(str(i) for i in items)}"
        return f"Agregar «{a.get('texto', '?')}» a la lista {ref}"
    if accion in ("marcar", "desmarcar"):
        return f"{accion.capitalize()} el item {a.get('item_id')}"
    if accion in ("eliminar_item", "borrar_item"):
        return f"Eliminar el item {a.get('item_id')}"
    if accion in ("eliminar_lista", "borrar_lista"):
        return f"Eliminar la lista {ref}"
    return f"Listas: {accion}"


def _describe_cancelar_recordatorio(a: dict) -> str:
    return f"Cancelar el recordatorio {_recordatorio_ref(a)}"


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
    return f"Editar el evento {_evento_ref(a)} -> {cambios}"


def _describe_cancelar_evento(a: dict) -> str:
    return f"Cancelar el evento {_evento_ref(a)}"


def _describe_exportar_ics(a: dict) -> str:
    rango = ""
    if a.get("desde") or a.get("hasta"):
        rango = f" (desde {a.get('desde', '...')} hasta {a.get('hasta', '...')})"
    return f"Exportar los eventos a un archivo .ics{rango}"


def _describe_sincronizar_calendario(a: dict) -> str:
    return "Sincronizar el calendario local con Google Calendar"


def _describe_gestionar_temporizador(a: dict) -> str:
    accion = str(a.get("accion", "?")).lower()
    if accion in ("iniciar", "empezar", "crear", "nueva", "nuevo", "start", "comenzar"):
        if (a.get("tipo") or "").lower() == "pomodoro":
            suf = f" «{a['etiqueta']}»" if a.get("etiqueta") else ""
            return f"Iniciar un Pomodoro{suf} (25 min de trabajo)"
        suf = f" «{a['etiqueta']}»" if a.get("etiqueta") else ""
        return f"Iniciar un temporizador de {a.get('minutos', '?')} min{suf}"
    if accion in ("cancelar", "parar", "detener", "terminar", "stop"):
        ref = a.get("etiqueta") or a.get("id") or "activo"
        return f"Cancelar el temporizador {ref}"
    if accion in ("pausar", "pausa"):
        ref = a.get("etiqueta") or a.get("id") or "activo"
        return f"Pausar el temporizador {ref}"
    if accion in ("reanudar", "reanuda", "continuar"):
        ref = a.get("etiqueta") or a.get("id") or "activo"
        return f"Reanudar el temporizador {ref}"
    return f"Temporizador: {accion}"


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
                    "padre_id": {
                        "type": "integer",
                        "description": (
                            "Id de la tarea padre si esto es una SUBTAREA "
                            "(opcional)."
                        ),
                    },
                    **_etiquetas_prop(),
                },
                "required": ["titulo"],
            },
            "func": tasks.crear_tarea,
            "kind": WRITE,
            "describe": _describe_crear_tarea,
        },
        {
            "name": "listar_tareas",
            "description": (
                "Lista las tareas guardadas con filtros opcionales. Para rangos de "
                "fecha usa 'periodo' (hoy, esta_semana, proximos_dias, etc.)."
            ),
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
                    "vencidas": {
                        "type": "boolean",
                        "description": (
                            "Solo tareas cuya fecha limite YA PASO (atrasadas/vencidas)"
                        ),
                    },
                    "limite": {"type": "integer", "description": "Maximo de resultados"},
                    "desde": {"type": "string", "description": "Fecha ISO inicial (opcional)"},
                    "hasta": {"type": "string", "description": "Fecha ISO final (opcional)"},
                    "incluir_subtareas": {
                        "type": "boolean",
                        "description": (
                            "Si es true (por defecto), cada tarea incluye sus "
                            "'subtareas' anidadas."
                        ),
                    },
                    **_etiqueta_filtro_prop(),
                    **_periodo_props(),
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
                    "padre_id": {
                        "type": "integer",
                        "description": "Id de la tarea padre (para convertirla en subtarea).",
                    },
                    **_etiquetas_prop(),
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
                "Usa 'cuando' en formato ISO (YYYY-MM-DD HH:MM) y en el futuro. "
                "Para repeticiones, indica 'recurrencia'."
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
                    "recurrencia": {
                        "type": "string",
                        "enum": ["ninguna", "diaria", "semanal", "mensual"],
                        "description": "Repeticion (por defecto ninguna)",
                    },
                    **_etiquetas_prop(),
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
                        "enum": [
                            "pendientes",
                            "enviados",
                            "cancelados",
                            "historial",
                            "todos",
                        ],
                        "description": (
                            "Que recordatorios listar. 'historial' = pendientes + "
                            "enviados (sin cancelados); 'todos' incluye cancelados. "
                            "Por defecto 'pendientes'."
                        ),
                    },
                    "vencidos": {
                        "type": "boolean",
                        "description": (
                            "Solo recordatorios cuya hora YA PASO y siguen pendientes"
                        ),
                    },
                    "limite": {"type": "integer"},
                    "desde": {"type": "string", "description": "Fecha ISO inicial (opcional)"},
                    "hasta": {"type": "string", "description": "Fecha ISO final (opcional)"},
                    **_etiqueta_filtro_prop(),
                    **_periodo_props(),
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
                    **_etiquetas_prop(),
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
                "desde ahora; cada evento incluye 'faltan' (tiempo restante, ya "
                "calculado). Para rangos relativos usa 'periodo'; para 'el mas proximo' "
                "usa limite=1; para 'el mas antiguo' usa orden='antiguos'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "Fecha ISO inicial (opcional)"},
                    "hasta": {"type": "string", "description": "Fecha ISO final (opcional)"},
                    "incluir_cancelados": {"type": "boolean"},
                    "pasados": {
                        "type": "boolean",
                        "description": (
                            "Solo eventos que YA OCURRIERON (inicio anterior a ahora). "
                            "Por defecto se listan los proximos."
                        ),
                    },
                    "orden": {
                        "type": "string",
                        "enum": ["proximos", "antiguos"],
                        "description": (
                            "proximos (por defecto) o antiguos (todo el historial, el "
                            "mas viejo primero)."
                        ),
                    },
                    "limite": {"type": "integer"},
                    **_etiqueta_filtro_prop(),
                    **_periodo_props(),
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
                    **_etiquetas_prop(),
                },
                "required": ["id"],
            },
            "func": calendar.editar_evento,
            "kind": WRITE,
            "describe": _describe_editar_evento,
        },
        {
            "name": "cancelar_evento",
            "description": (
                "Cancela un evento por su id o por su titulo. Usa el id EXACTO del "
                "evento que el usuario menciona (del ultimo listado); no lo inventes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Id del evento"},
                    "titulo": {
                        "type": "string",
                        "description": "Texto parcial del titulo del evento",
                    },
                },
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
        {
            "name": "sincronizar_calendario",
            "description": (
                "Sincroniza el calendario local con Google Calendar "
                "(bidireccional): trae los eventos nuevos/cambiados de Google y "
                "sube los cambios locales pendientes. Usala cuando el usuario diga "
                "'sincroniza mi calendario' o 'actualiza el calendario con Google'."
            ),
            "parameters": {"type": "object", "properties": {}},
            "func": gcal.sincronizar,
            "kind": WRITE,
            "describe": _describe_sincronizar_calendario,
        },
        {
            "name": "consultar_notas",
            "description": (
                "Lee notas de texto libre. accion 'listar' (por defecto) o 'buscar' "
                "(por 'texto'). Filtra por fecha de creacion con 'periodo'/'dias' o "
                "'desde'/'hasta'; 'orden' = recientes (por defecto) o antiguas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "enum": ["listar", "buscar"],
                        "description": "listar (por defecto) o buscar",
                    },
                    "texto": {
                        "type": "string",
                        "description": "Texto a buscar (accion buscar)",
                    },
                    "desde": {"type": "string", "description": "Fecha ISO inicial (opcional)"},
                    "hasta": {"type": "string", "description": "Fecha ISO final (opcional)"},
                    "orden": {
                        "type": "string",
                        "enum": ["recientes", "antiguas"],
                        "description": "recientes (por defecto) o antiguas (la mas vieja primero)",
                    },
                    "limite": {"type": "integer", "description": "Maximo de resultados"},
                    **_etiqueta_filtro_prop(),
                    **_periodo_props(),
                },
            },
            "func": notes.consultar_notas,
            "kind": READ,
        },
        {
            "name": "gestionar_notas",
            "description": (
                "Crea, edita o elimina notas de texto libre. accion 'crear' (titulo, "
                "contenido), 'editar' (id + campos) o 'eliminar' (id)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "enum": ["crear", "editar", "eliminar"],
                    },
                    "id": {
                        "type": "integer",
                        "description": "Id de la nota (editar/eliminar)",
                    },
                    "titulo": {"type": "string"},
                    "contenido": {"type": "string"},
                    **_etiquetas_prop(),
                },
                "required": ["accion"],
            },
            "func": notes.gestionar_notas,
            "kind": WRITE,
            "describe": _describe_gestionar_notas,
        },
        {
            "name": "consultar_listas",
            "description": (
                "Lee listas/checklists. accion 'listar' (todas, con sus items) o 'ver' "
                "(items de una lista por 'id' o 'nombre')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string", "enum": ["listar", "ver"]},
                    "id": {"type": "integer"},
                    "nombre": {"type": "string"},
                },
            },
            "func": lists.consultar_listas,
            "kind": READ,
        },
        {
            "name": "gestionar_listas",
            "description": (
                "Crea y modifica listas/checklists. accion: crear (nombre + 'items' "
                "opcional para crearla con sus elementos de una vez), agregar (lista + "
                "'texto' o 'items'), marcar/desmarcar (item_id), eliminar_item "
                "(item_id) o eliminar_lista (id/nombre)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "enum": [
                            "crear",
                            "agregar",
                            "marcar",
                            "desmarcar",
                            "eliminar_item",
                            "eliminar_lista",
                        ],
                    },
                    "id": {"type": "integer", "description": "Id de la lista"},
                    "nombre": {"type": "string", "description": "Nombre de la lista"},
                    "texto": {
                        "type": "string",
                        "description": "Texto del item a agregar",
                    },
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Elementos de la lista (crear/agregar, varios de golpe)",
                    },
                    "item_id": {"type": "integer", "description": "Id del item"},
                    "hecho": {
                        "type": "boolean",
                        "description": "Marcar como hecho (por defecto true)",
                    },
                },
                "required": ["accion"],
            },
            "func": lists.gestionar_listas,
            "kind": WRITE,
            "describe": _describe_gestionar_listas,
        },
        {
            "name": "buscar_todo",
            "description": (
                "Busca un texto en TODOS los datos locales a la vez (tareas, notas, "
                "eventos, recordatorios y listas). Usala para 'busca X', 'donde esta "
                "X' o 'encuentra X' cuando NO se especifica un dominio. Devuelve los "
                "resultados agrupados por dominio."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Texto a buscar (palabra o frase).",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Maximo de resultados por dominio (por defecto 10).",
                    },
                    "dominios": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "tareas",
                                "notas",
                                "eventos",
                                "recordatorios",
                                "listas",
                            ],
                        },
                        "description": "Opcional: limita la busqueda a estos dominios.",
                    },
                },
                "required": ["texto"],
            },
            "func": search.buscar_todo,
            "kind": READ,
        },
        {
            "name": "listar_etiquetas",
            "description": (
                "Lista todas las etiquetas/categorias usadas (tareas, notas, eventos "
                "y recordatorios) con cuantas veces aparecen y en que dominios."
            ),
            "parameters": {"type": "object", "properties": {}},
            "func": search.listar_etiquetas,
            "kind": READ,
        },
        {
            "name": "consultar_temporizador",
            "description": (
                "Muestra los temporizadores y pomodoros ACTIVOS y cuanto falta para "
                "que suenen. Usala para 'cuanto queda del pomodoro' o 'que "
                "temporizadores tengo'."
            ),
            "parameters": {"type": "object", "properties": {}},
            "func": timers.estado,
            "kind": READ,
        },
        {
            "name": "gestionar_temporizador",
            "description": (
                "Inicia o cancela temporizadores y pomodoros. accion 'iniciar' (tipo "
                "pomodoro|temporizador, 'minutos', 'etiqueta') o 'cancelar' (id o "
                "etiqueta). Se ejecuta AL INSTANTE (sin confirmacion). El pomodoro es "
                "de 25 min de trabajo y 5 de descanso (descanso largo cada 4)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "enum": ["iniciar", "cancelar", "pausar", "reanudar"],
                    },
                    "tipo": {
                        "type": "string",
                        "enum": ["temporizador", "pomodoro"],
                        "description": "Por defecto temporizador.",
                    },
                    "minutos": {
                        "type": "integer",
                        "description": "Duracion en minutos (temporizador).",
                    },
                    "etiqueta": {
                        "type": "string",
                        "description": "Nombre del temporizador (p. ej. 'horno').",
                    },
                    "id": {
                        "type": "integer",
                        "description": "Id del temporizador (cancelar/pausar/reanudar).",
                    },
                    "trabajo_min": {
                        "type": "integer",
                        "description": "Minutos de trabajo del pomodoro (opcional).",
                    },
                    "descanso_min": {
                        "type": "integer",
                        "description": "Minutos de descanso del pomodoro (opcional).",
                    },
                },
                "required": ["accion"],
            },
            "func": timers.gestionar,
            "kind": READ,
            "describe": _describe_gestionar_temporizador,
        },
    ]
