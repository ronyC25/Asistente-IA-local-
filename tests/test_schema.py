from __future__ import annotations

from src.brain.schema import build_tools


def test_tools_esperadas_presentes():
    names = {t["name"] for t in build_tools()}
    esperadas = {
        "crear_tarea",
        "listar_tareas",
        "completar_tarea",
        "editar_tarea",
        "eliminar_tarea",
        "fecha_hora_actual",
        "crear_recordatorio",
        "listar_recordatorios",
        "cancelar_recordatorio",
        "enviar_notificacion_windows",
        "enviar_telegram",
        "leer_email",
        "enviar_email",
    }
    assert esperadas <= names


def test_flags_lectura_escritura():
    tools = {t["name"]: t for t in build_tools()}
    assert tools["enviar_email"]["kind"] == "write"
    assert tools["enviar_telegram"]["kind"] == "write"
    assert tools["leer_email"]["kind"] == "read"
    assert tools["listar_tareas"]["kind"] == "read"
