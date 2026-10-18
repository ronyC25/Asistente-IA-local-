from __future__ import annotations

import pytest

from src import config
from src.tools import calendar, lists, notes, reminders, search, tasks


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database", str(tmp_path / "test.db"))
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        dict(config.settings.google_calendar, enabled=False),
    )
    tasks._conn().close()
    notes._conn().close()
    reminders._conn().close()
    calendar._conn().close()
    lists._conn().close()
    yield


def _poblar() -> None:
    tasks.crear_tarea("Comprar leche", etiquetas=["compras", "hogar"])
    notes.gestionar_notas(
        "crear", titulo="Receta", contenido="leche y harina", etiquetas=["ideas"]
    )
    reminders.crear_recordatorio("tomar leche", "2030-01-01 09:00", etiquetas="salud")
    calendar.crear_evento("Cita leche", "2030-01-02 10:00", etiquetas=["trabajo"])
    lists.gestionar_listas("crear", nombre="Compra semanal", items=["leche", "pan"])


def test_buscar_todo_agrupa():
    _poblar()
    res = search.buscar_todo("leche")
    assert res["total"] == 5
    assert len(res["tareas"]) == 1
    assert len(res["notas"]) == 1
    assert len(res["recordatorios"]) == 1
    assert len(res["eventos"]) == 1
    assert len(res["listas"]) == 1


def test_buscar_todo_filtra_dominios():
    _poblar()
    res = search.buscar_todo("leche", dominios=["tareas"])
    assert "tareas" in res
    assert "notas" not in res
    assert res["total"] == 1


def test_buscar_todo_limite():
    for i in range(5):
        tasks.crear_tarea(f"tarea leche {i}")
    res = search.buscar_todo("leche", limite=2)
    assert len(res["tareas"]) == 2


def test_buscar_todo_requiere_texto():
    with pytest.raises(ValueError):
        search.buscar_todo("   ")


def test_listar_etiquetas():
    _poblar()
    res = search.listar_etiquetas()
    nombres = {e["etiqueta"] for e in res["etiquetas"]}
    assert {"compras", "hogar", "ideas", "salud", "trabajo"} <= nombres
    compras = next(e for e in res["etiquetas"] if e["etiqueta"] == "compras")
    assert compras["dominios"]["tareas"] == 1
