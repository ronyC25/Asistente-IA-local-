from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import config
from src.tools import timers


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database", str(tmp_path / "test.db"))
    monkeypatch.setattr(
        config.settings,
        "pomodoro",
        {**config.settings.pomodoro, "presintetizar": False},
    )
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
        assert timers.avanzar(t["id"]) is True
        r = timers.obtener(t["id"])
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
    assert timers.avanzar(t["id"]) is True
    assert timers.listar("completados")["total"] == 1


def test_avanzar_atomico_solo_una_vez():
    t = timers.iniciar(minutos=1)
    assert timers.avanzar(t["id"], t["fin"]) is True
    # segundo intento con el mismo 'fin': ya no esta activo -> no reclama
    assert timers.avanzar(t["id"], t["fin"]) is False


def test_pausar_y_reanudar():
    t = timers.iniciar(minutos=10)
    p = timers.pausar(id=t["id"])
    assert p["estado"] == "pausado"
    assert p["restante_seg"] > 0
    # pausado no aparece en vencidos
    assert timers.vencidos((datetime.now() + timedelta(hours=1)).isoformat()) == []
    r = timers.reanudar(id=t["id"])
    assert r["estado"] == "activo"


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


def test_aviso_preparado():
    t = timers.iniciar(minutos=1, etiqueta="horno")
    texto, _wav = timers.aviso(t["id"])
    assert texto and "horno" in texto


def test_scheduler_avisa_timer(monkeypatch):
    from src import scheduler
    from src.tools import reminders

    t = timers.iniciar(minutos=1, tipo="temporizador")
    monkeypatch.setattr(timers, "vencidos", lambda *a, **k: [dict(t)])
    monkeypatch.setattr(reminders, "vencidos", lambda *a, **k: [])
    avisos: list[str] = []
    monkeypatch.setattr(
        scheduler, "_dispatch_aviso", lambda txt, wav=None: avisos.append(txt)
    )
    scheduler.check_due()
    assert avisos and "Temporizador" in avisos[0]
    assert timers.listar("completados")["total"] == 1


def test_avisar_avatar_local(monkeypatch):
    import httpx

    from src import avatar, scheduler

    monkeypatch.setattr(avatar, "notificar_avatar", lambda *a, **k: True)
    llamado: list = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: llamado.append(1))
    scheduler._avisar_avatar("hola")
    assert llamado == []


def test_avisar_avatar_fallback_http(monkeypatch):
    import httpx

    from src import avatar, scheduler

    avatar._CLIENTES.clear()
    avatar._LOOP = None
    urls: list[str] = []
    monkeypatch.setattr(httpx, "post", lambda url, **k: urls.append(url))
    scheduler._avisar_avatar("hola")
    assert urls and urls[0].endswith("/avatar/say")
