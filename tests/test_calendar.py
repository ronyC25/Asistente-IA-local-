from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import config
from src.tools import calendar


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    config.settings.database = str(tmp_path / "test.db")
    calendar._conn().close()
    yield tmp_path


def _futuro(dias: int = 1) -> str:
    return (datetime.now() + timedelta(days=dias)).isoformat(timespec="minutes")


def test_crear_y_listar():
    e = calendar.crear_evento("Reunion", _futuro(1), lugar="Oficina")
    assert e["titulo"] == "Reunion"
    assert e["lugar"] == "Oficina"
    assert e["estado"] == "activo"
    assert calendar.listar_eventos()["total"] == 1


def test_fin_antes_de_inicio():
    with pytest.raises(ValueError):
        calendar.crear_evento("X", _futuro(2), fin=_futuro(1))


def test_editar():
    e = calendar.crear_evento("Cita", _futuro(1))
    r = calendar.editar_evento(e["id"], titulo="Cita medica", lugar="Clinica")
    assert r["titulo"] == "Cita medica"
    assert r["lugar"] == "Clinica"


def test_cancelar():
    e = calendar.crear_evento("Cumple", _futuro(1))
    c = calendar.cancelar_evento(e["id"])
    assert c["estado"] == "cancelado"
    assert calendar.listar_eventos()["total"] == 0
    assert calendar.listar_eventos(incluir_cancelados=True)["total"] == 1


def test_exportar_ics(tmp_path):
    calendar.crear_evento("Evento A", _futuro(1), notas="con, comas; y punto")
    r = calendar.exportar_ics()
    assert r["ok"] is True
    assert r["eventos_exportados"] == 1
    contenido = open(r["archivo"], encoding="utf-8").read()
    assert "BEGIN:VCALENDAR" in contenido
    assert "BEGIN:VEVENT" in contenido
    assert "SUMMARY:Evento A" in contenido
    assert "END:VCALENDAR" in contenido
