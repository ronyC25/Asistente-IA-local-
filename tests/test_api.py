from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src import config
from src.api import app
from src.tools import timers


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database", str(tmp_path / "test.db"))
    monkeypatch.setattr(
        config.settings,
        "pomodoro",
        {**config.settings.pomodoro, "presintetizar": False},
    )
    timers._conn().close()
    return TestClient(app)


def test_temporizadores_get_inicial(client):
    r = client.get("/temporizadores")
    assert r.status_code == 200
    data = r.json()
    assert data["temporizadores"] == []
    assert data["config"]["trabajo_min"] == config.settings.pomodoro["trabajo_min"]


def test_temporizador_crear_y_listar(client):
    r = client.post(
        "/temporizadores",
        json={"tipo": "temporizador", "minutos": 10, "etiqueta": "horno"},
    )
    assert r.status_code == 200
    tid = r.json()["id"]
    data = client.get("/temporizadores").json()
    assert len(data["temporizadores"]) == 1
    assert data["temporizadores"][0]["id"] == tid


def test_temporizador_pausar_reanudar_cancelar(client):
    tid = client.post(
        "/temporizadores", json={"tipo": "temporizador", "minutos": 10}
    ).json()["id"]

    assert client.post(f"/temporizadores/{tid}/pausar").json()["estado"] == "pausado"
    assert client.post(f"/temporizadores/{tid}/reanudar").json()["estado"] == "activo"
    assert client.post(f"/temporizadores/{tid}/cancelar").json()["estado"] == "cancelado"
    assert client.get("/temporizadores").json()["temporizadores"] == []


def test_temporizador_accion_invalida(client):
    tid = client.post(
        "/temporizadores", json={"tipo": "temporizador", "minutos": 10}
    ).json()["id"]
    r = client.post(f"/temporizadores/{tid}/bailar")
    assert r.status_code == 400


def test_temporizador_sin_minutos(client):
    r = client.post("/temporizadores", json={"tipo": "temporizador"})
    assert r.status_code == 400


def test_avatar_say_sin_clientes(client):
    from src import avatar

    avatar._CLIENTES.clear()
    avatar._LOOP = None
    r = client.post("/avatar/say", json={"texto": "hola"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_avatar_say_con_wav(client):
    from src import avatar

    avatar._CLIENTES.clear()
    avatar._LOOP = None
    r = client.post("/avatar/say", json={"texto": "hola", "wav_b64": "AAAA"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_temporizadores_con_wav_serializa(client):
    """Con aviso_wav (bytes no-UTF8) no debe romper la serializacion JSON (bug 500)."""
    from src.tools import timers

    tid = client.post(
        "/temporizadores", json={"tipo": "temporizador", "minutos": 10}
    ).json()["id"]
    # simular la pre-sintesis: WAV con bytes invalidos en UTF-8
    conn = timers._conn()
    conn.execute(
        "UPDATE timers SET aviso_wav = ? WHERE id = ?", (b"\xff\xfe\x00\xa7", tid)
    )
    conn.commit()
    conn.close()

    r = client.get("/temporizadores")
    assert r.status_code == 200
    t = r.json()["temporizadores"][0]
    assert t["id"] == tid
    assert "aviso_wav" not in t  # el BLOB no debe filtrarse

    r2 = client.post(f"/temporizadores/{tid}/pausar")
    assert r2.status_code == 200
    assert r2.json()["estado"] == "pausado"
