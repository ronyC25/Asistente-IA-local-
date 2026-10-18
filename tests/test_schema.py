from __future__ import annotations

import pytest

from src import config
from src.brain.schema import _describe_eliminar, build_tools
from src.tools import tasks


@pytest.fixture
def tmp_db(tmp_path):
    config.settings.database = str(tmp_path / "test.db")
    tasks._conn().close()
    yield


def test_describe_eliminar_muestra_titulo(tmp_db):
    t = tasks.crear_tarea("Cenar Broster")
    txt = _describe_eliminar({"id": t["id"]})
    assert "Cenar Broster" in txt
    assert str(t["id"]) in txt


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
        "consultar_notas",
        "gestionar_notas",
        "consultar_listas",
        "gestionar_listas",
        "buscar_todo",
        "listar_etiquetas",
    }
    assert esperadas <= names


def test_flags_lectura_escritura():
    tools = {t["name"]: t for t in build_tools()}
    assert tools["enviar_email"]["kind"] == "write"
    assert tools["enviar_telegram"]["kind"] == "write"
    assert tools["leer_email"]["kind"] == "read"
    assert tools["listar_tareas"]["kind"] == "read"
    assert tools["gestionar_notas"]["kind"] == "write"
    assert tools["consultar_notas"]["kind"] == "read"
    assert tools["gestionar_listas"]["kind"] == "write"
    assert tools["consultar_listas"]["kind"] == "read"
    assert tools["buscar_todo"]["kind"] == "read"
    assert tools["listar_etiquetas"]["kind"] == "read"
