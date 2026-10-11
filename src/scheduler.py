"""Scheduler de recordatorios (APScheduler, polling cada 30s)."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

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
    """Envia los recordatorios cuya hora ya paso."""
    from .tools import reminders

    for r in reminders.vencidos():
        try:
            _dispatch(r["canal"], r["texto"])
            reminders.marcar_enviado(r["id"])
            log.info("recordatorio enviado id=%s canal=%s", r["id"], r["canal"])
        except Exception as exc:  # noqa: BLE001
            reminders.marcar_error(r["id"])
            log.warning("fallo el recordatorio id=%s: %s", r["id"], exc)


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
