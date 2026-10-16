"""Sincronizacion con Google Calendar (bidireccional, OAuth 2.0).

- SQLite sigue siendo la fuente de verdad; los cambios locales se empujan a Google.
- ``pull_incremental`` trae los cambios de Google usando el ``syncToken``.
- Los conflictos se resuelven segun ``google_calendar.conflict_policy``
  (por defecto gana el cambio mas reciente; empate -> local).

Nunca debe romper el flujo local: si no hay red/token, lanza ``NoConfigurado``
o propaga el error y el llamante decide (el CRUD local usa push best-effort).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..config import settings

log = logging.getLogger("asistente.gcal")

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class NoConfigurado(RuntimeError):
    """Google Calendar no esta configurado o autorizado."""


def _cfg() -> dict:
    return settings.google_calendar


# --- deteccion de estado / credenciales ---
def disponible() -> bool:
    """True si la sincronizacion esta activada y existen credenciales + token."""
    from pathlib import Path

    cfg = _cfg()
    if not cfg.get("enabled"):
        return False
    return Path(cfg["credentials_file"]).exists() and Path(cfg["token_file"]).exists()


def esta_conectado() -> bool:
    try:
        return disponible()
    except Exception:  # noqa: BLE001
        return False


def zona_horaria() -> str | None:
    """Zona IANA configurada o auto-detectada (None = usar solo el offset)."""
    cfg = _cfg()
    if cfg.get("timezone"):
        return cfg["timezone"]
    try:
        from tzlocal import get_localzone_name

        return get_localzone_name()
    except Exception:  # noqa: BLE001
        return None


def _service():
    from pathlib import Path

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    cfg = _cfg()
    token = Path(cfg["token_file"])
    if not token.exists():
        raise NoConfigurado(
            "falta autorizar Google Calendar (ejecuta: start.ps1 -Mode auth)"
        )
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise NoConfigurado(
                "token de Google caducado o revocado; vuelve a autorizar "
                "(start.ps1 -Mode auth)"
            )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# --- mapeo local <-> Google ---
def _evento_a_google(ev: dict) -> dict:
    body: dict = {"summary": ev["titulo"]}
    tz = zona_horaria()
    ini = datetime.fromisoformat(ev["inicio"])
    if ev["todo_el_dia"]:
        body["start"] = {"date": ini.date().isoformat()}
        fin = datetime.fromisoformat(ev["fin"]) if ev["fin"] else ini + timedelta(days=1)
        body["end"] = {"date": fin.date().isoformat()}
    else:
        fin = datetime.fromisoformat(ev["fin"]) if ev["fin"] else ini + timedelta(hours=1)
        body["start"] = {"dateTime": ini.astimezone().isoformat()}
        body["end"] = {"dateTime": fin.astimezone().isoformat()}
        if tz:
            body["start"]["timeZone"] = tz
            body["end"]["timeZone"] = tz
    if ev.get("lugar"):
        body["location"] = ev["lugar"]
    if ev.get("notas"):
        body["description"] = ev["notas"]
    return body


def _google_a_local(g: dict) -> dict:
    start = g.get("start", {})
    end = g.get("end", {})
    if "date" in start:
        todo = True
        ini = datetime.fromisoformat(start["date"])
        fin = (
            datetime.fromisoformat(end["date"])
            if end.get("date")
            else ini + timedelta(days=1)
        )
    else:
        todo = False
        ini = datetime.fromisoformat(start["dateTime"]).astimezone().replace(tzinfo=None)
        fin = (
            datetime.fromisoformat(end["dateTime"]).astimezone().replace(tzinfo=None)
            if end.get("dateTime")
            else None
        )
    return {
        "titulo": g.get("summary") or "(sin titulo)",
        "inicio": ini.isoformat(),
        "fin": fin.isoformat() if fin else None,
        "todo_el_dia": todo,
        "lugar": g.get("location"),
        "notas": g.get("description"),
    }


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite datetime('now') es UTC
    return dt


def _gana_local(ev: dict, g: dict) -> bool:
    policy = _cfg().get("conflict_policy", "last_write_wins")
    if policy == "local_wins":
        return True
    if policy == "google_wins":
        return False
    local_t = _parse_ts(ev.get("actualizado_en"))
    google_t = _parse_ts(g.get("updated"))
    if local_t is None:
        return False
    if google_t is None:
        return True
    return local_t >= google_t


# --- operaciones ---
def push_evento(event_id: int) -> dict:
    """Sube (o borra en Google) un evento local concreto."""
    from . import calendar

    ev = calendar.obtener_evento(event_id)
    if ev is None:
        raise ValueError(f"no existe el evento {event_id}")
    service = _service()
    cal = _cfg()["calendar_id"]

    if ev["estado"] == "cancelado":
        if ev.get("gcal_id"):
            service.events().delete(calendarId=cal, eventId=ev["gcal_id"]).execute()
            calendar.guardar_gcal(event_id, None, None, None)
        calendar.marcar_sincronizado(event_id)
        return {"ok": True, "accion": "delete", "id": event_id}

    body = _evento_a_google(ev)
    if ev.get("gcal_id"):
        result = (
            service.events()
            .patch(calendarId=cal, eventId=ev["gcal_id"], body=body)
            .execute()
        )
    else:
        result = service.events().insert(calendarId=cal, body=body).execute()
    calendar.guardar_gcal(
        event_id, result["id"], result.get("updated"), result.get("etag")
    )
    calendar.marcar_sincronizado(event_id)
    return {"ok": True, "accion": "push", "id": event_id, "gcal_id": result["id"]}


def push_pendientes() -> dict:
    from . import calendar

    pendientes = calendar.listar_pendientes_push()
    subidos = 0
    errores: list[dict] = []
    for ev in pendientes:
        try:
            push_evento(ev["id"])
            subidos += 1
        except Exception as exc:  # noqa: BLE001
            errores.append({"id": ev["id"], "error": str(exc)})
    return {"total": len(pendientes), "subidos": subidos, "errores": errores}


def _aplicar_google(calendar, g: dict) -> str | None:
    gid = g["id"]
    ev = calendar.obtener_por_gcal(gid)
    cancelado = g.get("status") == "cancelled"

    if ev is None:
        if cancelado:
            return None
        datos = _google_a_local(g)
        calendar.upsert_desde_gcal(gid, datos, g.get("updated"), g.get("etag"))
        return "creado"

    if cancelado:
        if ev.get("pending_push") and _gana_local(ev, g):
            return None  # el local manda; se subira en push
        calendar.cancelar_por_gcal(gid)
        return "cancelado"

    if ev.get("pending_push") and _gana_local(ev, g):
        return None  # conflicto resuelto a favor del local
    datos = _google_a_local(g)
    calendar.actualizar_desde_gcal(gid, datos, g.get("updated"), g.get("etag"))
    return "actualizado"


def pull_incremental() -> dict:
    from . import calendar

    service = _service()
    cal = _cfg()["calendar_id"]
    token = calendar.get_sync_token(cal)
    creados = actualizados = cancelados = 0
    page_token = None
    while True:
        kwargs: dict = {"calendarId": cal, "singleEvents": True, "maxResults": 250}
        if token:
            kwargs["syncToken"] = token
        if page_token:
            kwargs["pageToken"] = page_token
        try:
            resp = service.events().list(**kwargs).execute()
        except Exception as exc:  # noqa: BLE001
            if token and "410" in str(exc):  # syncToken caducado -> resync completo
                calendar.set_sync_token(cal, None)
                token = None
                continue
            raise
        for g in resp.get("items", []):
            r = _aplicar_google(calendar, g)
            if r == "creado":
                creados += 1
            elif r == "actualizado":
                actualizados += 1
            elif r == "cancelado":
                cancelados += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            calendar.set_sync_token(cal, resp.get("nextSyncToken"))
            break
    calendar.set_last_sync(cal)
    return {
        "creados": creados,
        "actualizados": actualizados,
        "cancelados": cancelados,
    }


def sincronizar() -> dict:
    """Sincronizacion completa: primero trae de Google, luego sube lo pendiente."""
    if not disponible():
        raise NoConfigurado(
            "Google Calendar no esta configurado. Instala requirements-google.txt, "
            "autoriza con 'start.ps1 -Mode auth' y activa google_calendar.enabled."
        )
    pull = pull_incremental()
    push = push_pendientes()
    return {"ok": True, "pull": pull, "push": push}
