from __future__ import annotations

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
