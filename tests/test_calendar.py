from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import config
from src.tools import calendar


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database", str(tmp_path / "test.db"))
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        dict(config.settings.google_calendar, enabled=False),
    )
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


def test_listar_pasados():
    calendar.crear_evento(
        "Ayer",
        (datetime.now() - timedelta(days=1)).isoformat(timespec="minutes"),
    )
    calendar.crear_evento("Manana", _futuro(1))
    pasados = calendar.listar_eventos(pasados=True)
    assert pasados["total"] == 1
    assert pasados["eventos"][0]["titulo"] == "Ayer"
    assert calendar.listar_eventos()["total"] == 1  # proximos


def test_listar_periodo_manana():
    manana = (datetime.now() + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    calendar.crear_evento("Manana", manana.isoformat())
    lejos = (datetime.now() + timedelta(days=10)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    calendar.crear_evento("Lejos", lejos.isoformat())
    r = calendar.listar_eventos(periodo="manana")
    assert r["total"] == 1
    assert r["eventos"][0]["titulo"] == "Manana"


def test_listar_periodo_proximos_dias():
    hoy = datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)
    calendar.crear_evento("HoyTarde", hoy.isoformat())
    calendar.crear_evento("En5dias", (hoy + timedelta(days=5)).isoformat())
    r = calendar.listar_eventos(periodo="proximos_dias", dias=3)
    assert r["total"] == 1
    assert r["eventos"][0]["titulo"] == "HoyTarde"


def test_listar_orden_antiguos_con_faltan():
    pasado = (datetime.now() - timedelta(days=10)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    futuro = (datetime.now() + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    calendar.crear_evento("Viejo", pasado.isoformat())
    calendar.crear_evento("Nuevo", futuro.isoformat())
    r = calendar.listar_eventos(orden="antiguos", limite=1)
    assert r["total"] == 1
    assert r["eventos"][0]["titulo"] == "Viejo"
    assert r["eventos"][0]["faltan"].startswith("hace")


def test_listar_proximo_tiene_faltan():
    futuro = (datetime.now() + timedelta(hours=2)).replace(
        minute=0, second=0, microsecond=0
    )
    calendar.crear_evento("Proximo", futuro.isoformat())
    r = calendar.listar_eventos(limite=1)
    assert r["eventos"][0]["titulo"] == "Proximo"
    assert r["eventos"][0]["faltan"].startswith("en")


def test_listar_evento_mismo_dia():
    dia = (datetime.now() + timedelta(days=5)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    calendar.crear_evento("EventoDia", dia.isoformat())
    fecha = dia.date().isoformat()
    r = calendar.listar_eventos(desde=fecha, hasta=fecha)
    assert r["total"] == 1
    assert r["eventos"][0]["titulo"] == "EventoDia"


def test_etiquetas_y_filtro():
    e = calendar.crear_evento("Reunion", _futuro(1), etiquetas=["Trabajo"])
    assert e["etiquetas"] == ["trabajo"]
    assert calendar.listar_eventos(etiqueta="trabajo")["total"] == 1
    assert calendar.listar_eventos(etiqueta="otra")["total"] == 0
