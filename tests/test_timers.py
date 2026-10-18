from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import config
from src.tools import timers


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database", str(tmp_path / "test.db"))
    timers._conn().close()
    yield


def _futuro(minutos: int = 10) -> str:
    return (datetime.now() + timedelta(minutes=minutos)).isoformat()


def test_iniciar_temporizador_y_pomodoro():
    t = timers.iniciar(minutos=10, etiqueta="horno", tipo="temporizador")
    assert t["tipo"] == "temporizador"
    assert t["duracion_min"] == 10
    assert t["etiqueta"] == "horno"
    assert t["estado"] == "activo"

    p = timers.iniciar(tipo="pomodoro")
    assert p["tipo"] == "pomodoro"
    assert p["fase"] == "trabajo"
    assert p["ciclo"] == 1
    assert p["duracion_min"] == config.settings.pomodoro["trabajo_min"]


def test_temporizador_sin_minutos():
    with pytest.raises(ValueError):
        timers.iniciar(tipo="temporizador")


def test_multiples_y_cancelar():
    a = timers.iniciar(minutos=5, etiqueta="horno")
    b = timers.iniciar(tipo="pomodoro")
    assert timers.estado()["total"] == 2

    c = timers.cancelar(etiqueta="horno")
    assert c["id"] == a["id"]
    assert c["estado"] == "cancelado"

    # queda uno: cancelar sin indicar funciona
    c2 = timers.cancelar()
    assert c2["id"] == b["id"]


def test_cancelar_ambiguo():
    timers.iniciar(minutos=5)
    timers.iniciar(minutos=6)
    with pytest.raises(ValueError):
        timers.cancelar()


def test_estado_faltan():
    timers.iniciar(minutos=10)
    r = timers.estado()
    assert r["total"] == 1
    assert r["temporizadores"][0]["faltan"].startswith("en")


def test_pomodoro_ciclos():
    t = timers.iniciar(tipo="pomodoro")
    fases = []
    for _ in range(7):
        r = timers.avanzar(t["id"])
        fases.append((r["fase"], r["ciclo"]))
    assert fases == [
        ("descanso", 1),
        ("trabajo", 2),
        ("descanso", 2),
        ("trabajo", 3),
        ("descanso", 3),
        ("trabajo", 4),
        ("descanso_largo", 4),
    ]


def test_temporizador_avanzar_completa():
    t = timers.iniciar(minutos=1)
    assert timers.avanzar(t["id"]) is None
    assert timers.listar("completados")["total"] == 1


def test_vencidos():
    timers.iniciar(minutos=5)
    futuro = (datetime.now() + timedelta(minutes=10)).isoformat()
    assert len(timers.vencidos(futuro)) == 1
    assert len(timers.vencidos((datetime.now() - timedelta(minutes=1)).isoformat())) == 0


def test_mensaje_aviso():
    p = timers.iniciar(tipo="pomodoro")
    assert "trabajo del ciclo 1" in timers.mensaje_aviso(p)
    t = timers.iniciar(minutos=1, etiqueta="horno")
    msg = timers.mensaje_aviso(t)
    assert "Temporizador" in msg and "horno" in msg


def test_scheduler_avisa_timer(monkeypatch):
    from src import scheduler
    from src.tools import reminders

    t = timers.iniciar(minutos=1, tipo="temporizador")
    monkeypatch.setattr(timers, "vencidos", lambda *a, **k: [dict(t)])
    monkeypatch.setattr(reminders, "vencidos", lambda *a, **k: [])
    avisos: list[str] = []
    monkeypatch.setattr(scheduler, "_dispatch_aviso", lambda txt: avisos.append(txt))
    scheduler.check_due()
    assert avisos and "Temporizador" in avisos[0]
    assert timers.listar("completados")["total"] == 1
