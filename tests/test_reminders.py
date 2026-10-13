from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import config
from src.tools import reminders


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    db = tmp_path / "test.db"
    config.settings.database = str(db)
    reminders._conn().close()
    yield


def _futuro(minutos: int = 60) -> str:
    return (datetime.now() + timedelta(minutes=minutos)).isoformat(timespec="minutes")


def test_crear_y_listar():
    r = reminders.crear_recordatorio("Llamar al medico", _futuro(30))
    assert r["texto"] == "Llamar al medico"
    assert r["estado"] == "pendiente"
    assert r["canal"] == "windows"

    resultado = reminders.listar_recordatorios()
    assert resultado["total"] == 1


def test_no_permite_fecha_pasada():
    pasado = (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes")
    with pytest.raises(ValueError):
        reminders.crear_recordatorio("Tarde", pasado)


def test_canal_invalido():
    with pytest.raises(ValueError):
        reminders.crear_recordatorio("X", _futuro(), canal="paloma")


def test_cancelar():
    r = reminders.crear_recordatorio("Cita", _futuro())
    c = reminders.cancelar_recordatorio(r["id"])
    assert c["estado"] == "cancelado"
    assert reminders.listar_recordatorios("pendientes")["total"] == 0
    assert reminders.listar_recordatorios("cancelados")["total"] == 1


def test_vencidos_y_marcar_enviado():
    r = reminders.crear_recordatorio("Ahora", _futuro(1))
    # simulamos que ya paso la hora
    fut = (datetime.now() + timedelta(hours=2)).isoformat()
    assert len(reminders.vencidos(fut)) == 1
    reminders.marcar_enviado(r["id"])
    assert reminders.listar_recordatorios("enviados")["total"] == 1
    assert reminders.vencidos(fut) == []


def test_recurrencia_diaria():
    r = reminders.crear_recordatorio("Tomar agua", _futuro(), recurrencia="diaria")
    assert r["recurrencia"] == "diaria"
    nxt = reminders.siguiente_ocurrencia(r["cuando"], "diaria")
    assert nxt is not None and nxt > r["cuando"]


def test_recurrencia_invalida():
    with pytest.raises(ValueError):
        reminders.crear_recordatorio("X", _futuro(), recurrencia="cada_luna")


def test_siguiente_ocurrencia_ninguna():
    assert reminders.siguiente_ocurrencia(_futuro(), "ninguna") is None
    assert reminders.siguiente_ocurrencia(_futuro(), None) is None


def test_reprogramar_recurrente():
    r = reminders.crear_recordatorio("X", _futuro(1), recurrencia="semanal")
    nuevo = reminders.siguiente_ocurrencia(r["cuando"], "semanal")
    r2 = reminders.reprogramar(r["id"], nuevo)
    assert r2["estado"] == "pendiente"
    assert r2["cuando"] == nuevo


def test_scheduler_reprograma_recurrente(monkeypatch):
    from src import scheduler

    r = reminders.crear_recordatorio("Y", _futuro(), recurrencia="diaria")
    monkeypatch.setattr(reminders, "vencidos", lambda *a, **k: [dict(r)])
    monkeypatch.setattr(scheduler, "_dispatch", lambda canal, texto: {"ok": True})
    scheduler.check_due()
    actualizado = reminders.listar_recordatorios("pendientes")["recordatorios"][0]
    assert actualizado["id"] == r["id"]
    assert actualizado["cuando"] != r["cuando"]
    assert actualizado["estado"] == "pendiente"


def test_listar_vencidos():
    r = reminders.crear_recordatorio("Vencido", _futuro(5))
    reminders.crear_recordatorio("Futuro", _futuro(120))
    pasado = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes")
    reminders.reprogramar(r["id"], pasado)
    vencidos = reminders.listar_recordatorios(vencidos=True)
    assert vencidos["total"] == 1
    assert vencidos["recordatorios"][0]["texto"] == "Vencido"


def test_listar_historial_excluye_cancelados():
    r1 = reminders.crear_recordatorio("Uno", _futuro(10))
    r2 = reminders.crear_recordatorio("Dos", _futuro(20))
    reminders.marcar_enviado(r1["id"])
    reminders.cancelar_recordatorio(r2["id"])

    historial = reminders.listar_recordatorios("historial")
    textos = {x["texto"] for x in historial["recordatorios"]}
    assert "Uno" in textos  # enviado: si
    assert "Dos" not in textos  # cancelado: excluido

    todos = reminders.listar_recordatorios("todos")
    assert {x["texto"] for x in todos["recordatorios"]} == {"Uno", "Dos"}
