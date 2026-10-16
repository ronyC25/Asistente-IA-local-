"""Calendario local: eventos en SQLite con exportacion a formato .ics.

La sincronizacion con Google Calendar (bidireccional, OAuth) vive en
``src/tools/gcal.py``; aqui solo se guarda el estado (``gcal_id``, ``pending_push``...)
y se hace un push *best-effort* al crear/editar/cancelar.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from ..config import settings
from ..db import connect
from ..timeutil import faltan_texto, parse_datetime, resolver_periodo

log = logging.getLogger("asistente.calendar")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo        TEXT NOT NULL,
    inicio        TEXT NOT NULL,
    fin           TEXT,
    todo_el_dia   INTEGER NOT NULL DEFAULT 0,
    lugar         TEXT,
    notas         TEXT,
    estado        TEXT NOT NULL DEFAULT 'activo',
    creado_en     TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now')),
    gcal_id       TEXT,
    gcal_updated  TEXT,
    gcal_etag     TEXT,
    pending_push  INTEGER NOT NULL DEFAULT 0
);
"""

_SYNC_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_meta (
    calendar_id TEXT PRIMARY KEY,
    sync_token  TEXT,
    last_sync   TEXT
);
"""

# Columnas anadidas despues (migracion de BD existentes).
_GCAL_COLUMNS = {
    "gcal_id": "TEXT",
    "gcal_updated": "TEXT",
    "gcal_etag": "TEXT",
    "pending_push": "INTEGER NOT NULL DEFAULT 0",
}


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(_SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)")}
    for name, decl in _GCAL_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {name} {decl}")
    conn.execute(_SYNC_META_SCHEMA)
    conn.commit()


def _row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["todo_el_dia"] = bool(d["todo_el_dia"])
    if "pending_push" in d:
        d["pending_push"] = bool(d["pending_push"])
    return d


def _refetch(id: int) -> dict:
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (int(id),)).fetchone()
    finally:
        conn.close()
    return _row(row)


def _push_best_effort(event_id: int) -> None:
    """Intenta subir el evento a Google si esta conectado (nunca rompe el flujo local)."""
    try:
        from . import gcal

        if gcal.esta_conectado():
            gcal.push_evento(event_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("push a Google diferido (evento %s): %s", event_id, exc)


def _find(conn: sqlite3.Connection, id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (int(id),)).fetchone()
    if row is None:
        raise ValueError(f"no existe ningun evento con id {id}")
    return row


def crear_evento(
    titulo: str,
    inicio: str,
    fin: str | None = None,
    todo_el_dia: bool = False,
    lugar: str | None = None,
    notas: str | None = None,
) -> dict:
    if not titulo or not str(titulo).strip():
        raise ValueError("el titulo del evento no puede estar vacio")
    ini = parse_datetime(inicio)
    fin_dt = parse_datetime(fin) if fin else None
    if fin_dt is not None and fin_dt < ini:
        raise ValueError("la fecha de fin no puede ser anterior al inicio")
    conn = _conn()
    try:
        cur = conn.execute(
            """INSERT INTO events
               (titulo, inicio, fin, todo_el_dia, lugar, notas, pending_push)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (
                str(titulo).strip(),
                ini.isoformat(),
                fin_dt.isoformat() if fin_dt else None,
                1 if todo_el_dia else 0,
                lugar,
                notas,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()
    _push_best_effort(row["id"])
    return _refetch(row["id"])


def listar_eventos(
    desde: str | None = None,
    hasta: str | None = None,
    incluir_cancelados: bool = False,
    limite: int = 100,
    pasados: bool = False,
    periodo: str | None = None,
    dias: int | None = None,
    orden: str | None = None,
) -> dict:
    where: list[str] = []
    params: list = []
    if not incluir_cancelados:
        where.append("estado = 'activo'")
    o = str(orden or "").lower()
    buscar_todo = o in ("antiguos", "antiguo")
    if periodo:
        d, h = resolver_periodo(periodo, dias)
        where.append("inicio >= ?")
        params.append(d.isoformat())
        where.append("inicio <= ?")
        params.append(h.isoformat())
    else:
        if desde:
            where.append("inicio >= ?")
            params.append(parse_datetime(desde).isoformat())
        elif not pasados and not buscar_todo:
            where.append("inicio >= ?")
            params.append(datetime.now().isoformat())
        if hasta:
            where.append("inicio <= ?")
            params.append(parse_datetime(hasta).isoformat())
        elif pasados:
            where.append("inicio < ?")
            params.append(datetime.now().isoformat())
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    if o in ("antiguos", "antiguo", "asc"):
        direccion = "ASC"
    elif o in ("recientes", "desc"):
        direccion = "DESC"
    else:
        direccion = "DESC" if pasados else "ASC"
    conn = _conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM events {clause} ORDER BY inicio {direccion}, id {direccion} "
            "LIMIT ?",
            (*params, int(limite)),
        ).fetchall()
    finally:
        conn.close()
    ahora = datetime.now()
    eventos: list[dict] = []
    for r in rows:
        d = _row(r)
        try:
            d["faltan"] = faltan_texto(datetime.fromisoformat(d["inicio"]), ahora)
        except (ValueError, TypeError):
            d["faltan"] = None
        eventos.append(d)
    return {"total": len(eventos), "eventos": eventos}


def obtener_evento(id: int) -> dict | None:
    """Devuelve un evento por id (o None). Para describir propuestas."""
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (int(id),)).fetchone()
    finally:
        conn.close()
    return _row(row) if row is not None else None


def editar_evento(
    id: int,
    titulo: str | None = None,
    inicio: str | None = None,
    fin: str | None = None,
    todo_el_dia: bool | None = None,
    lugar: str | None = None,
    notas: str | None = None,
    estado: str | None = None,
) -> dict:
    conn = _conn()
    try:
        row = _find(conn, id)
        sets: list[str] = []
        params: list = []
        if titulo:
            sets.append("titulo = ?")
            params.append(str(titulo).strip())
        if inicio is not None:
            sets.append("inicio = ?")
            params.append(parse_datetime(inicio).isoformat())
        if fin is not None:
            sets.append("fin = ?")
            params.append(parse_datetime(fin).isoformat())
        if todo_el_dia is not None:
            sets.append("todo_el_dia = ?")
            params.append(1 if todo_el_dia else 0)
        if lugar is not None:
            sets.append("lugar = ?")
            params.append(lugar)
        if notas is not None:
            sets.append("notas = ?")
            params.append(notas)
        if estado is not None:
            est = str(estado).strip().lower()
            if est not in {"activo", "cancelado"}:
                raise ValueError("estado no valido: usa activo o cancelado")
            sets.append("estado = ?")
            params.append(est)
        if not sets:
            return _row(row)
        sets.append("actualizado_en = datetime('now')")
        sets.append("pending_push = 1")
        params.append(row["id"])
        conn.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    _push_best_effort(row["id"])
    return _refetch(row["id"])


def cancelar_evento(id: int) -> dict:
    conn = _conn()
    try:
        row = _find(conn, id)
        if row["estado"] != "cancelado":
            conn.execute(
                "UPDATE events SET estado = 'cancelado', "
                "actualizado_en = datetime('now'), pending_push = 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM events WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    _push_best_effort(row["id"])
    return _refetch(row["id"])


# --- soporte de sincronizacion con Google Calendar ---
def listar_pendientes_push() -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE pending_push = 1 ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def obtener_por_gcal(gcal_id: str) -> dict | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM events WHERE gcal_id = ?", (gcal_id,)
        ).fetchone()
    finally:
        conn.close()
    return _row(row) if row is not None else None


def guardar_gcal(
    id: int, gcal_id: str | None, updated: str | None, etag: str | None
) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE events SET gcal_id = ?, gcal_updated = ?, gcal_etag = ? WHERE id = ?",
            (gcal_id, updated, etag, int(id)),
        )
        conn.commit()
    finally:
        conn.close()


def marcar_sincronizado(id: int) -> None:
    conn = _conn()
    try:
        conn.execute("UPDATE events SET pending_push = 0 WHERE id = ?", (int(id),))
        conn.commit()
    finally:
        conn.close()


def upsert_desde_gcal(
    gcal_id: str, datos: dict, updated: str | None, etag: str | None
) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            """INSERT INTO events
               (titulo, inicio, fin, todo_el_dia, lugar, notas,
                gcal_id, gcal_updated, gcal_etag, pending_push)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                datos["titulo"],
                datos["inicio"],
                datos["fin"],
                1 if datos["todo_el_dia"] else 0,
                datos.get("lugar"),
                datos.get("notas"),
                gcal_id,
                updated,
                etag,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def actualizar_desde_gcal(
    gcal_id: str, datos: dict, updated: str | None, etag: str | None
) -> None:
    conn = _conn()
    try:
        conn.execute(
            """UPDATE events SET titulo = ?, inicio = ?, fin = ?, todo_el_dia = ?,
               lugar = ?, notas = ?, gcal_updated = ?, gcal_etag = ?,
               pending_push = 0, actualizado_en = datetime('now')
               WHERE gcal_id = ?""",
            (
                datos["titulo"],
                datos["inicio"],
                datos["fin"],
                1 if datos["todo_el_dia"] else 0,
                datos.get("lugar"),
                datos.get("notas"),
                updated,
                etag,
                gcal_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def cancelar_por_gcal(gcal_id: str) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE events SET estado = 'cancelado', pending_push = 0, "
            "actualizado_en = datetime('now') WHERE gcal_id = ?",
            (gcal_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_sync_token(calendar_id: str) -> str | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT sync_token FROM sync_meta WHERE calendar_id = ?", (calendar_id,)
        ).fetchone()
    finally:
        conn.close()
    return row["sync_token"] if row is not None else None


def set_sync_token(calendar_id: str, token: str | None) -> None:
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO sync_meta (calendar_id, sync_token, last_sync)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(calendar_id) DO UPDATE SET
                 sync_token = excluded.sync_token, last_sync = datetime('now')""",
            (calendar_id, token),
        )
        conn.commit()
    finally:
        conn.close()


def set_last_sync(calendar_id: str) -> None:
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO sync_meta (calendar_id, last_sync) VALUES (?, datetime('now'))
               ON CONFLICT(calendar_id) DO UPDATE SET last_sync = datetime('now')""",
            (calendar_id,),
        )
        conn.commit()
    finally:
        conn.close()


# --- exportacion .ics ---
def _escape(text: str | None) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _vevent(row: sqlite3.Row) -> list[str]:
    ini = datetime.fromisoformat(row["inicio"])
    todo_el_dia = bool(row["todo_el_dia"])
    lines = [
        "BEGIN:VEVENT",
        f"UID:evento-{row['id']}@asistente-local",
        f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
    ]
    if todo_el_dia:
        lines.append(f"DTSTART;VALUE=DATE:{_fmt_date(ini)}")
        fin = datetime.fromisoformat(row["fin"]) if row["fin"] else ini + timedelta(days=1)
        lines.append(f"DTEND;VALUE=DATE:{_fmt_date(fin)}")
    else:
        lines.append(f"DTSTART:{_fmt_dt(ini)}")
        fin = datetime.fromisoformat(row["fin"]) if row["fin"] else ini + timedelta(hours=1)
        lines.append(f"DTEND:{_fmt_dt(fin)}")
    lines.append(f"SUMMARY:{_escape(row['titulo'])}")
    if row["lugar"]:
        lines.append(f"LOCATION:{_escape(row['lugar'])}")
    if row["notas"]:
        lines.append(f"DESCRIPTION:{_escape(row['notas'])}")
    lines.append("END:VEVENT")
    return lines


def exportar_ics(
    desde: str | None = None,
    hasta: str | None = None,
    ruta: str | None = None,
) -> dict:
    # Si no se indica rango, se exportan TODOS los eventos (no solo los proximos).
    eventos = listar_eventos(
        desde=desde or "1970-01-01", hasta=hasta, limite=10000
    )["eventos"]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Asistente IA local//ES",
        "CALSCALE:GREGORIAN",
    ]
    for ev in eventos:
        lines.extend(_vevent(ev))
    lines.append("END:VCALENDAR")

    destino = Path(ruta) if ruta else Path(settings.database).parent / "calendario.ics"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return {
        "ok": True,
        "archivo": str(destino),
        "eventos_exportados": len(eventos),
    }
