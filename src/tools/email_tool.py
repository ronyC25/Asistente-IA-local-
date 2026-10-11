"""Correo electronico: lectura por IMAP y envio por SMTP."""
from __future__ import annotations

import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage

from ..config import settings


def _require_imap() -> None:
    if not settings.email_address or not settings.email_password:
        raise ValueError("Faltan EMAIL_ADDRESS y EMAIL_PASSWORD en .env.")
    if not settings.imap_host:
        raise ValueError("Falta IMAP_HOST en .env.")


def _require_smtp() -> None:
    if not settings.email_address or not settings.email_password:
        raise ValueError("Faltan EMAIL_ADDRESS y EMAIL_PASSWORD en .env.")
    if not settings.smtp_host:
        raise ValueError("Falta SMTP_HOST en .env.")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeDecodeError, ValueError):
        return value


def _snippet(msg: email.message.Message, limite: int = 300) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True) or b""
                body = payload.decode(charset, errors="replace")
                break
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True) or b""
        body = payload.decode(charset, errors="replace")
    body = " ".join(body.split())
    return body[:limite]


def leer_email(
    carpeta: str = "INBOX",
    limite: int = 5,
    no_leidos: bool = False,
) -> dict:
    _require_imap()
    limite = max(1, int(limite))
    try:
        conn = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        conn.login(settings.email_address, settings.email_password)
    except (imaplib.IMAP4.error, OSError) as exc:
        raise ValueError(f"no se pudo conectar al buzon IMAP: {exc}") from exc
    try:
        conn.select(carpeta)
        criteria = "UNSEEN" if no_leidos else "ALL"
        typ, data = conn.search(None, criteria)
        if typ != "OK" or not data or not data[0]:
            return {"total": 0, "correos": []}
        ids = data[0].split()[-limite:]
        correos = []
        for num in reversed(ids):
            typ, raw = conn.fetch(num, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            correos.append(
                {
                    "de": _decode(msg.get("From")),
                    "asunto": _decode(msg.get("Subject")),
                    "fecha": _decode(msg.get("Date")),
                    "resumen": _snippet(msg),
                }
            )
    finally:
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    return {"total": len(correos), "correos": correos}


def enviar_email(destinatario: str, asunto: str, cuerpo: str) -> dict:
    if not destinatario or "@" not in str(destinatario):
        raise ValueError("el destinatario no es valido")
    _require_smtp()
    msg = EmailMessage()
    msg["From"] = settings.email_address
    msg["To"] = destinatario
    msg["Subject"] = asunto or "(sin asunto)"
    msg.set_content(cuerpo or "")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.email_address, settings.email_password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise ValueError(f"no se pudo enviar el correo: {exc}") from exc
    return {"ok": True, "canal": "email", "para": destinatario, "asunto": asunto}
