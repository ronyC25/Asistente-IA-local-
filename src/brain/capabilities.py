"""Lista de capacidades del asistente (respuesta determinista y completa).

Se genera a partir del registro de herramientas para que nunca quede incompleta
ni se trunque por el limite de tokens del modelo.
"""
from __future__ import annotations

_GRUPOS = (
    (
        "Tareas y subtareas",
        ("crear_tarea", "listar_tareas", "completar_tarea", "editar_tarea", "eliminar_tarea"),
        "crear, listar, completar, editar y eliminar tareas (prioridad, fecha limite, "
        "etiquetas y subtareas).",
    ),
    (
        "Recordatorios",
        ("crear_recordatorio", "listar_recordatorios", "cancelar_recordatorio"),
        "programar avisos (con repeticion diaria, semanal o mensual) y consultarlos.",
    ),
    (
        "Notas",
        ("consultar_notas", "gestionar_notas"),
        "guardar, buscar, editar y eliminar notas de texto libre (con etiquetas).",
    ),
    (
        "Listas / checklists",
        ("consultar_listas", "gestionar_listas"),
        "crear listas y anadir, marcar o eliminar sus elementos.",
    ),
    (
        "Busqueda y etiquetas",
        ("buscar_todo", "listar_etiquetas"),
        "buscar en todos tus datos a la vez y ver las etiquetas que usas.",
    ),
    (
        "Calendario",
        (
            "crear_evento",
            "listar_eventos",
            "editar_evento",
            "cancelar_evento",
            "exportar_ics",
            "sincronizar_calendario",
        ),
        "gestionar eventos, exportarlos a .ics y sincronizar con Google Calendar.",
    ),
    (
        "Mensajeria y correo",
        ("enviar_notificacion_windows", "enviar_telegram", "leer_email", "enviar_email"),
        "avisos en Windows, mensajes por Telegram y leer o enviar correo.",
    ),
    (
        "Sistema",
        ("fecha_hora_actual",),
        "consultar la fecha y la hora actual.",
    ),
)

_EJEMPLOS = (
    "Anade una tarea: comprar leche (prioridad alta)",
    "Que eventos tengo manana?",
    "Recuerdame llamar al banco el viernes a las 9",
    "Busca donde apunte lo del proyecto",
    "Crea una lista de la compra con leche y pan",
)


def texto_capacidades(registry=None, nombre: str | None = None) -> str:
    """Devuelve la lista de capacidades agrupada (solo las herramientas existentes)."""
    if nombre is None:
        try:
            from ..config import settings

            nombre = settings.assistant_name
        except Exception:  # noqa: BLE001
            nombre = "el asistente"

    existentes = set(registry.names()) if registry is not None else None
    lineas = [f"Soy {nombre}. Esto es lo que puedo hacer:", ""]
    for titulo, tools, desc in _GRUPOS:
        if existentes is not None and not (set(tools) & existentes):
            continue
        lineas.append(f"- {titulo}: {desc}")
    lineas += ["", "Prueba a decir:"]
    lineas += [f"  - {e}" for e in _EJEMPLOS]
    return "\n".join(lineas)
