from __future__ import annotations

import pytest

from src.brain.registry import Registry
from src.brain.router import grupos_para, nombres, todos_los_grupos
from src.brain.schema import build_tools


def _registry() -> Registry:
    r = Registry()
    for spec in build_tools():
        r.add(spec)
    return r


class _Sesion:
    def __init__(self, grupos=None, pending=None):
        self.grupos = set(grupos or [])
        self.pending = pending


@pytest.mark.parametrize(
    "texto, grupo",
    [
        ("que tareas tengo", "tareas"),
        ("crea un evento el 28 de octubre", "eventos"),
        ("recuerdame llamar al banco", "recordatorios"),
        ("crea una nota sobre el proyecto", "notas"),
        ("crea una lista de la compra", "listas"),
        ("lee mis correos", "email"),
        ("manda un mensaje por telegram", "mensajeria"),
        ("pon un temporizador de 10 minutos", "temporizadores"),
        ("busca las llaves del coche", "busqueda"),
    ],
)
def test_grupo_por_dominio(texto, grupo):
    assert grupo in grupos_para(texto)


def test_notificaciones_consulta_es_recordatorio():
    grupos = grupos_para("que notificaciones tengo")
    assert "recordatorios" in grupos
    assert "mensajeria" not in grupos


def test_notificacion_accion_es_mensajeria():
    grupos = grupos_para("manda una notificacion al escritorio")
    assert "mensajeria" in grupos
    assert "recordatorios" not in grupos


def test_multi_dominio():
    grupos = grupos_para("manda las tareas por telegram")
    assert {"tareas", "mensajeria"} <= grupos


def test_saludo_solo_core():
    assert grupos_para("hola") == {"core"}


def test_accion_desconocida_usa_todas():
    assert grupos_para("crea algo raro") == todos_los_grupos()


def test_pending_conserva_grupos_previos():
    sesion = _Sesion(grupos={"eventos"}, pending=[("crear_evento", {})])
    grupos = grupos_para("si", sesion)
    assert "eventos" in grupos


def test_nombres_y_filtro_registry():
    r = _registry()
    names = nombres({"tareas"})
    assert "listar_tareas" in names
    assert "enviar_email" not in names
    schemas = r.schemas(names)
    assert {s["function"]["name"] for s in schemas} == names
    assert len(schemas) < len(r.schemas())
