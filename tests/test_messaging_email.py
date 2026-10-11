from __future__ import annotations

import pytest

from src import config
from src.tools import email_tool, messaging


def test_telegram_sin_token():
    config.settings.telegram_bot_token = None
    config.settings.telegram_chat_id = None
    with pytest.raises(ValueError):
        messaging.enviar_telegram("hola")


def test_telegram_sin_chat_id():
    config.settings.telegram_bot_token = "123:abc"
    config.settings.telegram_chat_id = None
    with pytest.raises(ValueError):
        messaging.enviar_telegram("hola")


def test_telegram_mensaje_vacio():
    config.settings.telegram_bot_token = "123:abc"
    config.settings.telegram_chat_id = "1"
    with pytest.raises(ValueError):
        messaging.enviar_telegram("")


def test_email_sin_config():
    config.settings.email_address = None
    config.settings.email_password = None
    with pytest.raises(ValueError):
        email_tool.leer_email()
    with pytest.raises(ValueError):
        email_tool.enviar_email("a@b.com", "x", "y")


def test_email_destinatario_invalido():
    config.settings.email_address = "me@x.com"
    config.settings.email_password = "pw"
    config.settings.smtp_host = "smtp.x.com"
    with pytest.raises(ValueError):
        email_tool.enviar_email("no-es-email", "x", "y")


def test_resolve_chat_id():
    config.settings.telegram_chat_id = "999"
    assert messaging._resolve_chat_id("default") == "999"
    assert messaging._resolve_chat_id("") == "999"
    assert messaging._resolve_chat_id(None) == "999"
    assert messaging._resolve_chat_id("-100123") == "-100123"


def test_enviar_telegram_ignora_chat_id_invalido(monkeypatch):
    config.settings.telegram_bot_token = "123:abc"
    config.settings.telegram_chat_id = "999"
    capturado = {}

    class _Resp:
        def json(self):
            return {"ok": True, "result": {"message_id": 1}}

    def _fake_post(url, json, timeout):
        capturado.update(json)
        return _Resp()

    monkeypatch.setattr(messaging.httpx, "post", _fake_post)
    res = messaging.enviar_telegram("hola", chat_id="default")
    assert capturado["chat_id"] == "999"
    assert res["chat_id"] == "999"
