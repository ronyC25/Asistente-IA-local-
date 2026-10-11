"""Mensajeria via Telegram Bot API."""
from __future__ import annotations

import re

import httpx

from ..config import settings

_API = "https://api.telegram.org"

_CHAT_ID_RE = re.compile(r"-?\d+")


def _require_token() -> str:
    token = settings.telegram_bot_token
    if not token:
        raise ValueError(
            "Falta TELEGRAM_BOT_TOKEN en .env. Crea un bot con @BotFather y "
            "copia el token."
        )
    return token


def _resolve_chat_id(chat_id: str | None) -> str:
    cid = str(chat_id).strip() if chat_id is not None else ""
    # Si no es un id numerico valido (p. ej. el modelo inventa 'default'),
    # se usa el chat configurado en .env.
    if not _CHAT_ID_RE.fullmatch(cid):
        cid = (settings.telegram_chat_id or "").strip()
    if not cid:
        raise ValueError(
            "Falta TELEGRAM_CHAT_ID en .env. Ejecuta "
            "'python -m src.tools.messaging' para descubrirlo."
        )
    return str(cid)


def enviar_telegram(mensaje: str, chat_id: str | None = None) -> dict:
    if not mensaje or not str(mensaje).strip():
        raise ValueError("el mensaje no puede estar vacio")
    token = _require_token()
    cid = _resolve_chat_id(chat_id)
    try:
        resp = httpx.post(
            f"{_API}/bot{token}/sendMessage",
            json={"chat_id": cid, "text": str(mensaje)},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise ValueError(f"no se pudo conectar con Telegram: {exc}") from exc
    data = resp.json()
    if not data.get("ok"):
        raise ValueError(f"Telegram respondio con error: {data.get('description')}")
    return {
        "ok": True,
        "canal": "telegram",
        "chat_id": cid,
        "message_id": data["result"]["message_id"],
    }


def obtener_chat_ids() -> list[dict]:
    """Lista los chats que han escrito al bot (para descubrir el chat_id)."""
    token = _require_token()
    resp = httpx.get(f"{_API}/bot{token}/getUpdates", timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise ValueError(f"Telegram respondio con error: {data.get('description')}")
    chats: dict[str, dict] = {}
    for update in data.get("result", []):
        msg = update.get("message") or update.get("edited_message") or {}
        chat = msg.get("chat")
        if chat:
            chats[str(chat["id"])] = {
                "chat_id": str(chat["id"]),
                "tipo": chat.get("type"),
                "nombre": chat.get("title")
                or " ".join(
                    filter(None, [chat.get("first_name"), chat.get("last_name")])
                )
                or chat.get("username"),
            }
    return list(chats.values())


def _main() -> None:
    print("Chats detectados (escribe algo a tu bot primero):")
    try:
        chats = obtener_chat_ids()
    except ValueError as exc:
        print(f"[!] {exc}")
        return
    if not chats:
        print("  (ninguno) Envia un mensaje a tu bot en Telegram y vuelve a intentar.")
        return
    for c in chats:
        print(f"  chat_id={c['chat_id']}  {c['nombre']} ({c['tipo']})")
    print("\nCopia el chat_id en TELEGRAM_CHAT_ID del archivo .env")


if __name__ == "__main__":
    _main()
