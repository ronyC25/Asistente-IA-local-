from __future__ import annotations

from datetime import datetime, timedelta

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


def test_listar_vencidas():
    pasado = (datetime.now() - timedelta(days=1)).isoformat(timespec="minutes")
    futuro = (datetime.now() + timedelta(days=2)).isoformat(timespec="minutes")
    tasks.crear_tarea("Atrasada", fecha_limite=pasado)
    tasks.crear_tarea("A tiempo", fecha_limite=futuro)
    tasks.crear_tarea("Sin fecha")

    vencidas = tasks.listar_tareas(vencidas=True)
    assert vencidas["total"] == 1
    assert vencidas["tareas"][0]["titulo"] == "Atrasada"

    # sin el filtro siguen apareciendo todas las pendientes
    assert tasks.listar_tareas()["total"] == 3


def test_listar_tareas_por_periodo():
    manana = (datetime.now() + timedelta(days=1)).date().isoformat()
    lejos = (datetime.now() + timedelta(days=10)).date().isoformat()
    tasks.crear_tarea("Manana", fecha_limite=manana)
    tasks.crear_tarea("Lejos", fecha_limite=lejos)
    tasks.crear_tarea("Sin fecha")
    r = tasks.listar_tareas(periodo="manana")
    assert r["total"] == 1
    assert r["tareas"][0]["titulo"] == "Manana"


def test_listar_tareas_faltan():
    futuro = (datetime.now() + timedelta(days=2)).isoformat(timespec="minutes")
    tasks.crear_tarea("X", fecha_limite=futuro)
    r = tasks.listar_tareas()
    assert r["tareas"][0]["faltan"].startswith("en")
