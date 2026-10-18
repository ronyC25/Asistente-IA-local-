from __future__ import annotations

import pytest

from src import config
from src.telegram_bot import TelegramBot


class _FakeAgent:
    def __init__(self, reply: str = "hola") -> None:
        self.reply = reply
        self.calls: list[str] = []

    def new_session(self):
        return object()

    def handle(self, session, text):
        self.calls.append(text)
        return self.reply, None


def _bot(monkeypatch, reply: str = "hola"):
    config.settings.telegram_bot_token = "123:abc"
    config.settings.telegram_chat_id = "999"
    agent = _FakeAgent(reply)
    bot = TelegramBot(agent=agent)
    enviados: list[tuple[str, str]] = []
    monkeypatch.setattr(bot, "_send", lambda cid, txt: enviados.append((cid, txt)))
    return bot, agent, enviados


def test_sin_token():
    config.settings.telegram_bot_token = None
    with pytest.raises(ValueError):
        TelegramBot()


def test_respuesta(monkeypatch):
    bot, agent, enviados = _bot(monkeypatch, reply="Tienes 2 tareas")
    bot.handle_update(
        {"update_id": 1, "message": {"chat": {"id": 999}, "text": "tareas"}}
    )
    assert agent.calls == ["tareas"]
    assert enviados == [("999", "Tienes 2 tareas")]


def test_chat_no_autorizado(monkeypatch):
    bot, agent, enviados = _bot(monkeypatch)
    bot.handle_update(
        {"update_id": 2, "message": {"chat": {"id": 555}, "text": "hola"}}
    )
    assert agent.calls == []
    assert enviados == []


def test_reset_limpia_sesion(monkeypatch):
    bot, agent, enviados = _bot(monkeypatch)
    bot._sessions["999"] = "algo"
    bot.handle_update(
        {"update_id": 3, "message": {"chat": {"id": 999}, "text": "/start@MiBot"}}
    )
    assert "999" not in bot._sessions
    assert agent.calls == []
    assert enviados and "Nueva conversacion" in enviados[0][1]


def test_sin_texto(monkeypatch):
    bot, _agent, enviados = _bot(monkeypatch)
    bot.handle_update({"update_id": 4, "message": {"chat": {"id": 999}}})
    assert enviados == []


def test_sesion_persistente(monkeypatch):
    bot, _agent, _enviados = _bot(monkeypatch)
    bot.handle_update(
        {"update_id": 5, "message": {"chat": {"id": 999}, "text": "uno"}}
    )
    primera = bot._sessions["999"]
    bot.handle_update(
        {"update_id": 6, "message": {"chat": {"id": 999}, "text": "dos"}}
    )
    assert bot._sessions["999"] is primera


def test_prime_offset(monkeypatch):
    bot, _agent, _enviados = _bot(monkeypatch)

    def _fake_get(method, **params):
        return [{"update_id": 42}] if method == "getUpdates" else []

    monkeypatch.setattr(bot, "_get", _fake_get)
    bot._prime_offset()
    assert bot._offset == 43


def test_ping(monkeypatch):
    bot, agent, enviados = _bot(monkeypatch)
    bot.handle_update(
        {"update_id": 9, "message": {"chat": {"id": 999}, "text": "/ping"}}
    )
    assert agent.calls == []
    assert enviados and enviados[0][1].startswith("pong")


def test_ayuda(monkeypatch):
    bot, agent, enviados = _bot(monkeypatch)
    bot.handle_update(
        {"update_id": 10, "message": {"chat": {"id": 999}, "text": "/ayuda"}}
    )
    assert agent.calls == []
    assert enviados and "Tareas" in enviados[0][1]


def test_split_message():
    from src.telegram_bot import _split_message

    assert _split_message("corto", 4096) == ["corto"]
    largo = "x" * 10000
    partes = _split_message(largo, 4096)
    assert len(partes) == 3
    assert "".join(partes) == largo


def test_send_verifica_error(monkeypatch):
    from src import telegram_bot

    config.settings.telegram_bot_token = "123:abc"
    config.settings.telegram_chat_id = "999"
    bot = TelegramBot(agent=_FakeAgent())

    class _Resp:
        def json(self):
            return {"ok": False, "description": "bad request"}

    monkeypatch.setattr(telegram_bot.httpx, "post", lambda *a, **k: _Resp())
    bot._send("999", "hola")  # no debe lanzar aunque Telegram devuelva ok:false
