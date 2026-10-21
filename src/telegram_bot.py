"""Bot de Telegram bidireccional.

Escucha los mensajes entrantes con *long polling* y los procesa con el agente,
manteniendo una **sesion persistente por chat** (asi la confirmacion "si/no"
funciona entre mensajes). Modo dedicado: ``python -m src.main --telegram``.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from .config import settings
from .factory import build_agent

log = logging.getLogger("asistente.telegram_bot")

_API = "https://api.telegram.org"

# Comandos que reinician la conversacion.
_COMANDOS_RESET = {"/start", "/reset", "/nueva", "/nuevo"}
_COMANDOS_PING = {"/ping"}
_COMANDOS_AYUDA = {"/ayuda", "/help", "/funciones", "/capacidades"}

# Limite de caracteres por mensaje de Telegram.
_TG_LIMIT = 4096


def _split_message(text: str, limit: int = _TG_LIMIT) -> list[str]:
    """Trocea un texto largo respetando saltos de linea/espacios."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    partes: list[str] = []
    resto = text
    while len(resto) > limit:
        corte = resto.rfind("\n", 0, limit)
        if corte <= 0:
            corte = resto.rfind(" ", 0, limit)
        if corte <= 0:
            corte = limit
        partes.append(resto[:corte])
        resto = resto[corte:].lstrip("\n")
    partes.append(resto)
    return partes


class TelegramBot:
    """Poller de Telegram que conecta los mensajes entrantes con el agente."""

    def __init__(self, poll_timeout: int = 25, agent=None) -> None:
        self.token = (settings.telegram_bot_token or "").strip()
        if not self.token:
            raise ValueError(
                "Falta TELEGRAM_BOT_TOKEN en .env. Crea un bot con @BotFather."
            )
        self.allowed_chat = (settings.telegram_chat_id or "").strip() or None
        self.poll_timeout = max(1, int(poll_timeout))
        self._agent = agent if agent is not None else build_agent()
        self._sessions: dict[str, object] = {}
        self._offset = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------- HTTP
    def _get(self, method: str, **params) -> list:
        resp = httpx.get(
            f"{_API}/bot{self.token}/{method}",
            params=params,
            timeout=self.poll_timeout + 10,
        )
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(data.get("description", "error desconocido de Telegram"))
        return data.get("result", [])

    def _send(self, chat_id: str, text: str) -> None:
        texto = (text or "").strip() or "(sin respuesta)"
        for parte in _split_message(texto):
            try:
                resp = httpx.post(
                    f"{_API}/bot{self.token}/sendMessage",
                    json={"chat_id": chat_id, "text": parte},
                    timeout=15,
                )
                data = resp.json()
                if not data.get("ok"):
                    log.warning(
                        "Telegram rechazo el mensaje: %s", data.get("description")
                    )
            except httpx.HTTPError as exc:  # noqa: BLE001
                log.warning("no se pudo enviar a Telegram: %s", exc)
            except ValueError:  # respuesta no-JSON
                log.warning("respuesta no-JSON de Telegram al enviar")

    # --------------------------------------------------------- sesiones
    def _session(self, chat_id: str):
        session = self._sessions.get(chat_id)
        if session is None:
            session = self._agent.new_session(
                session_id=chat_id, canal="telegram"
            )
            self._sessions[chat_id] = session
        return session

    def _es_comando(self, texto: str, comandos: set[str]) -> bool:
        # Admite "/start@MiBot".
        primera = texto.split()[0].split("@")[0].lower() if texto.split() else ""
        return primera in comandos

    def _responder(self, chat_id: str, texto: str) -> None:
        if self._es_comando(texto, _COMANDOS_RESET):
            self._sessions.pop(chat_id, None)
            reset = getattr(self._agent, "reset_session", None)
            if reset is not None:
                reset(chat_id)
            self._send(chat_id, "Nueva conversacion iniciada. En que te ayudo?")
            return
        if self._es_comando(texto, _COMANDOS_PING):
            self._send(chat_id, f"pong ({settings.model})")
            return
        if self._es_comando(texto, _COMANDOS_AYUDA):
            from .brain.capabilities import texto_capacidades

            self._send(
                chat_id, texto_capacidades(getattr(self._agent, "registry", None))
            )
            return
        try:
            session = self._session(chat_id)
            reply, _pending = self._agent.handle(session, texto)
            from .brain.emotions import limpiar_respuesta

            limpio, _emociones = limpiar_respuesta(reply or "")
            self._send(chat_id, limpio or "(sin respuesta)")
        except Exception as exc:  # noqa: BLE001
            log.exception("error procesando mensaje de Telegram")
            try:
                self._send(chat_id, f"Ocurrio un error: {exc}")
            except Exception:  # noqa: BLE001
                log.exception("tampoco se pudo enviar el error a Telegram")

    # ----------------------------------------------------------- updates
    def handle_update(self, update: dict) -> None:
        msg = update.get("message") or update.get("edited_message") or {}
        texto = (msg.get("text") or "").strip()
        if not texto:
            return
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        if not chat_id:
            return
        if self.allowed_chat and chat_id != self.allowed_chat:
            log.warning("mensaje ignorado de chat no autorizado: %s", chat_id)
            return
        log.info("mensaje de %s: %s", chat_id, texto[:100])
        self._responder(chat_id, texto)

    def _prime_offset(self) -> None:
        """Descarta el backlog: salta al ultimo update existente."""
        try:
            ultimos = self._get("getUpdates", offset=-1, timeout=0)
        except Exception as exc:  # noqa: BLE001
            log.warning("no se pudo leer el offset inicial: %s", exc)
            return
        if ultimos:
            self._offset = int(ultimos[-1].get("update_id", 0)) + 1

    def _loop(self) -> None:
        log.info("escuchando mensajes de Telegram...")
        while not self._stop.is_set():
            try:
                updates = self._get(
                    "getUpdates", offset=self._offset, timeout=self.poll_timeout
                )
            except Exception as exc:  # noqa: BLE001
                if self._stop.is_set():
                    break
                log.warning("getUpdates fallo: %s", exc)
                self._stop.wait(5)
                continue
            for update in updates:
                self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                try:
                    self.handle_update(update)
                except Exception:  # noqa: BLE001
                    log.exception("error manejando un update")

    # ------------------------------------------------------------- ciclo
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._prime_offset()
        self._thread = threading.Thread(
            target=self._loop, name="telegram-bot", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.poll_timeout + 5)


def _config_logging() -> None:
    """Registra la actividad del bot en ``data/telegram_bot.log``."""
    from .config import ROOT

    log_dir = ROOT / "data"
    log_dir.mkdir(exist_ok=True)
    handler = logging.FileHandler(log_dir / "telegram_bot.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.setLevel(logging.INFO)
    log.addHandler(handler)


def run() -> None:
    """Modo dedicado: bot + scheduler hasta Ctrl+C."""
    from .scheduler import shutdown as stop_scheduler
    from .scheduler import start as start_scheduler

    _config_logging()
    timeout = int(settings.telegram.get("poll_timeout", 25))
    bot = TelegramBot(poll_timeout=timeout)
    start_scheduler()
    bot.start()
    log.info("bot de Telegram en marcha (chat=%s)", bot.allowed_chat)
    print("Bot de Telegram en marcha. Escribe a tu bot (Ctrl+C para salir).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        bot.stop()
        stop_scheduler()


if __name__ == "__main__":
    run()
