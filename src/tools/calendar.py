"""Calendario local: eventos en SQLite con exportacion a formato .ics."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from ..config import settings
from ..db import connect
from ..timeutil import parse_datetime

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
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(_SCHEMA)
    return conn


def _row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["todo_el_dia"] = bool(d["todo_el_dia"])
    return d


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
               (titulo, inicio, fin, todo_el_dia, lugar, notas)
               VALUES (?, ?, ?, ?, ?, ?)""",
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
    return _row(row)


def listar_eventos(
    desde: str | None = None,
    hasta: str | None = None,
    incluir_cancelados: bool = False,
    limite: int = 100,
) -> dict:
    where: list[str] = []
    params: list = []
    if not incluir_cancelados:
        where.append("estado = 'activo'")
    ini = parse_datetime(desde) if desde else datetime.now()
    where.append("inicio >= ?")
    params.append(ini.isoformat())
    if hasta:
        where.append("inicio <= ?")
        params.append(parse_datetime(hasta).isoformat())
    clause = "WHERE " + " AND ".join(where)
    conn = _conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM events {clause} ORDER BY inicio LIMIT ?",
            (*params, int(limite)),
        ).fetchall()
    finally:
        conn.close()
    return {"total": len(rows), "eventos": [_row(r) for r in rows]}


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
        params.append(row["id"])
        conn.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    return _row(row)


def cancelar_evento(id: int) -> dict:
    conn = _conn()
    try:
        row = _find(conn, id)
        if row["estado"] != "cancelado":
            conn.execute(
                "UPDATE events SET estado = 'cancelado', actualizado_en = datetime('now') WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM events WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    return _row(row)


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
