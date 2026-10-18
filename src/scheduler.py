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
        try:
            _dispatch(r["canal"], r["texto"])
            nuevo = reminders.siguiente_ocurrencia(r["cuando"], r.get("recurrencia"))
            if nuevo:
                reminders.reprogramar(r["id"], nuevo)
                log.info(
                    "recordatorio %s enviado y reprogramado para %s", r["id"], nuevo
                )
            else:
                reminders.marcar_enviado(r["id"])
                log.info("recordatorio enviado id=%s canal=%s", r["id"], r["canal"])
        except Exception as exc:  # noqa: BLE001
            reminders.marcar_error(r["id"])
            log.warning("fallo el recordatorio id=%s: %s", r["id"], exc)

    from .tools import timers as timers_mod

    for t in timers_mod.vencidos():
        try:
            _dispatch_aviso(timers_mod.mensaje_aviso(t))
            timers_mod.avanzar(t["id"])
            log.info("temporizador %s avisado (%s)", t["id"], t.get("tipo"))
        except Exception as exc:  # noqa: BLE001
            log.warning("fallo el temporizador id=%s: %s", t["id"], exc)


def _dispatch_aviso(texto: str) -> None:
    """Aviso de temporizador/pomodoro: Telegram y/o avatar (voz), segun config."""
    cfg = getattr(settings, "pomodoro", {}) or {}
    if cfg.get("telegram", True):
        try:
            from .tools import messaging

            messaging.enviar_telegram(texto)
        except Exception as exc:  # noqa: BLE001
            log.warning("no se pudo enviar el aviso por Telegram: %s", exc)
    if cfg.get("avatar", True):
        try:
            from . import avatar

            avatar.notificar_avatar(texto)
        except Exception as exc:  # noqa: BLE001
            log.warning("no se pudo avisar al avatar: %s", exc)


def start(interval_seconds: int = 30) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
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
