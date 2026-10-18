"""Scheduler de recordatorios (APScheduler, polling cada 30s)."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings

log = logging.getLogger("asistente.scheduler")

_scheduler: BackgroundScheduler | None = None


def _dispatch(canal: str, texto: str) -> dict:
    if canal == "windows":
        from .tools import notify

        return notify.notify_windows("Jarvis - Recordatorio", texto)
    if canal == "telegram":
        from .tools import messaging

        return messaging.enviar_telegram(texto)
    raise ValueError(f"canal desconocido: {canal}")


def check_due() -> None:
    """Envia los recordatorios y temporizadores cuya hora ya paso."""
    from .tools import reminders

    for r in reminders.vencidos():
        # Reclamo atomico: solo uno de los procesos con scheduler despacha cada
        # recordatorio (evita doble envio).
        if not reminders.reclamar(r["id"]):
            continue
        try:
            _dispatch(r["canal"], r["texto"])
            nuevo = reminders.siguiente_ocurrencia(r["cuando"], r.get("recurrencia"))
            if nuevo:
                reminders.reprogramar(r["id"], nuevo)
                log.info(
                    "recordatorio %s enviado y reprogramado para %s", r["id"], nuevo
                )
            else:
                log.info("recordatorio enviado id=%s canal=%s", r["id"], r["canal"])
        except Exception as exc:  # noqa: BLE001
            reminders.marcar_error(r["id"])
            log.warning("fallo el recordatorio id=%s: %s", r["id"], exc)

    from .tools import timers as timers_mod

    for t in timers_mod.vencidos():
        # Texto/WAV pre-sintetizados (aviso inmediato).
        texto, wav = timers_mod.aviso(t["id"])
        if not texto:
            texto = timers_mod.mensaje_aviso(t)
        # Reclamo atomico (avanzar/completar solo si sigue activo con ese fin).
        if not timers_mod.avanzar(t["id"], t["fin"]):
            continue
        try:
            _dispatch_aviso(texto, wav)
            log.info("temporizador %s avisado (%s)", t["id"], t.get("tipo"))
        except Exception as exc:  # noqa: BLE001
            log.warning("fallo el aviso del temporizador id=%s: %s", t["id"], exc)


def _dispatch_aviso(texto: str, wav: bytes | None = None) -> None:
    """Aviso de temporizador/pomodoro: Telegram y/o avatar (voz), segun config."""
    cfg = getattr(settings, "pomodoro", {}) or {}
    if cfg.get("telegram", True):
        try:
            from .tools import messaging

            messaging.enviar_telegram(texto)
        except Exception as exc:  # noqa: BLE001
            log.warning("no se pudo enviar el aviso por Telegram: %s", exc)
    if cfg.get("avatar", True):
        _avisar_avatar(texto, wav)


def _avisar_avatar(texto: str, wav: bytes | None = None) -> None:
    """Hace hablar al avatar. Si este proceso no lo sirve, se lo pide al web."""
    try:
        from . import avatar

        if avatar.notificar_avatar(texto, wav):
            return
    except Exception as exc:  # noqa: BLE001
        log.debug("aviso al avatar local fallo: %s", exc)
    # Otro proceso (p. ej. el bot de Telegram) no tiene los WS del avatar:
    # se lo pedimos al servidor web, que es quien los sirve.
    try:
        import base64

        import httpx

        payload: dict = {"texto": texto}
        if wav:
            payload["wav_b64"] = base64.b64encode(wav).decode("ascii")
        httpx.post(
            f"http://127.0.0.1:{settings.port}/avatar/say",
            json=payload,
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("no se pudo avisar al avatar por HTTP: %s", exc)


def start(interval_seconds: int | None = None) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if interval_seconds is None:
        interval_seconds = int(
            (getattr(settings, "scheduler", None) or {}).get("tick_s", 1)
        )
    interval_seconds = max(1, int(interval_seconds))
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        check_due,
        "interval",
        seconds=interval_seconds,
        id="check_due",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("scheduler iniciado (cada %ss)", interval_seconds)
    return _scheduler


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def run_once() -> None:
    """Fuerza una revision inmediata (util para pruebas)."""
    check_due()
