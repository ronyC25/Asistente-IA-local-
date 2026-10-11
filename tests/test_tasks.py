from __future__ import annotations

import pytest

from src import config
from src.tools import tasks


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    db = tmp_path / "test.db"
    config.settings.database = str(db)
    tasks._conn().close()
    yield


def test_crear_y_listar():
    t = tasks.crear_tarea("Comprar leche", prioridad="alta")
    assert t["titulo"] == "Comprar leche"
    assert t["prioridad"] == "alta"
    assert t["estado"] == "pendiente"

    resultado = tasks.listar_tareas()
    assert resultado["total"] == 1
    assert resultado["tareas"][0]["id"] == t["id"]


def test_prioridad_invalida():
    with pytest.raises(ValueError):
        tasks.crear_tarea("X", prioridad="urgentísimo")


def test_completar_por_titulo():
    tasks.crear_tarea("Llamar a Juan")
    r = tasks.completar_tarea(titulo="Juan")
    assert r["estado"] == "completada"
    assert tasks.listar_tareas(estado="completadas")["total"] == 1
    assert tasks.listar_tareas(estado="pendientes")["total"] == 0


def test_titulo_ambiguo():
    tasks.crear_tarea("Pagar luz enero")
    tasks.crear_tarea("Pagar luz febrero")
    with pytest.raises(ValueError):
        tasks.completar_tarea(titulo="Pagar luz")


def test_editar_y_eliminar():
    t = tasks.crear_tarea("Borrador")
    e = tasks.editar_tarea(id=t["id"], nuevo_titulo="Final", prioridad="baja")
    assert e["titulo"] == "Final"
    assert e["prioridad"] == "baja"

    d = tasks.eliminar_tarea(id=t["id"])
    assert d["eliminada"] is True
    assert tasks.listar_tareas(estado="todas")["total"] == 0


def test_fecha_invalida():
    with pytest.raises(ValueError):
        tasks.crear_tarea("X", fecha_limite="mañana por la tarde")


def test_fecha_iso_valida():
    t = tasks.crear_tarea("Entrega", fecha_limite="2026-11-01")
    assert t["fecha_limite"].startswith("2026-11-01")
