from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from src.api import app
from src.config import settings

client = TestClient(app)


def test_avatar_config_endpoint():
    r = client.get("/avatar/config")
    assert r.status_code == 200
    data = r.json()
    assert data["default"] == settings.avatar["model"]
    assert isinstance(data["height"], int)
    assert data["lipsync_profile"] == "public/lipsync/profile.json"
    names = {m["name"] for m in data["models"]}
    assert "Haru" in names
    for m in data["models"]:
        assert m["path"].startswith("public/models/")


def test_avatar_settings_models():
    models = settings.avatar["models"]
    assert "Haru" in models
    assert "Wanko" in models
    assert all(p.endswith(".model3.json") for p in models.values())
    assert settings.avatar["height"] > 0


def test_notificar_avatar_sin_clientes():
    from src import avatar

    avatar._CLIENTES.clear()
    avatar._LOOP = None
    assert avatar.notificar_avatar("hola") is False


class _FakeWS:
    def __init__(self):
        self.json = []
        self.binary = []

    async def send_json(self, m):
        self.json.append(m)

    async def send_bytes(self, b):
        self.binary.append(b)


def test_hablar_en_avatares(monkeypatch):
    from src import avatar
    from src.voice import tts

    monkeypatch.setattr(tts, "sintetizar_wav_bytes", lambda t: b"WAV")
    ws = _FakeWS()
    avatar._CLIENTES.clear()
    avatar._CLIENTES.add(ws)
    try:
        asyncio.run(avatar._hablar_en_avatares("hola"))
    finally:
        avatar._CLIENTES.clear()
    assert any(m.get("type") == "reply" and m.get("text") == "hola" for m in ws.json)
    assert ws.binary == [b"WAV"]


def test_hablar_en_avatares_tolera_fallo_tts(monkeypatch):
    from src import avatar
    from src.voice import tts

    def boom(t):
        raise RuntimeError("sin tts")

    monkeypatch.setattr(tts, "sintetizar_wav_bytes", boom)
    ws = _FakeWS()
    avatar._CLIENTES.clear()
    avatar._CLIENTES.add(ws)
    try:
        asyncio.run(avatar._hablar_en_avatares("hola"))  # no debe lanzar
    finally:
        avatar._CLIENTES.clear()
    assert any(m.get("type") == "reply" for m in ws.json)
    assert ws.binary == []


def test_hablar_en_avatares_usa_wav_dado(monkeypatch):
    from src import avatar
    from src.voice import tts

    def boom(t):
        raise AssertionError("no debe sintetizar si se pasa el WAV")

    monkeypatch.setattr(tts, "sintetizar_wav_bytes", boom)
    ws = _FakeWS()
    avatar._CLIENTES.clear()
    avatar._CLIENTES.add(ws)
    try:
        asyncio.run(avatar._hablar_en_avatares("hola", b"WAV"))
    finally:
        avatar._CLIENTES.clear()
    assert ws.binary == [b"WAV"]
