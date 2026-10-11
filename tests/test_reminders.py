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
