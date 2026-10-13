"""Herramientas de recordatorios (persistidos en SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from dateutil.relativedelta import relativedelta

from ..config import settings
from ..db import connect
from ..timeutil import parse_datetime

_CANALES = {"windows", "telegram"}
_RECURRENCIAS = {"ninguna", "diaria", "semanal", "mensual"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    texto     TEXT NOT NULL,
    cuando    TEXT NOT NULL,
    canal     TEXT NOT NULL DEFAULT 'windows',
    recurrencia TEXT NOT NULL DEFAULT 'ninguna',
    estado    TEXT NOT NULL DEFAULT 'pendiente',
    creado_en TEXT NOT NULL DEFAULT (datetime('now')),
    enviado_en TEXT
);
"""

_ESTADO_FILTRO = {
    "pendientes": "pendiente",
    "pendiente": "pendiente",
    "enviados": "enviado",
    "enviado": "enviado",
    "cancelados": "cancelado",
    "cancelado": "cancelado",
    "todos": None,
    "todas": None,
}


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(_SCHEMA)
    # Migracion: anade la columna 'recurrencia' a bases de datos antiguas.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(reminders)")}
    if "recurrencia" not in cols:
        conn.execute(
            "ALTER TABLE reminders ADD COLUMN recurrencia TEXT NOT NULL DEFAULT 'ninguna'"
        )
        conn.commit()
    return conn


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def crear_recordatorio(
    texto: str,
    cuando: str,
    canal: str = "windows",
    recurrencia: str = "ninguna",
) -> dict:
    if not texto or not str(texto).strip():
        raise ValueError("el texto del recordatorio no puede estar vacio")
    canal = (canal or "windows").strip().lower()
    if canal not in _CANALES:
        raise ValueError(f"canal no valido: {canal}. Usa windows o telegram.")
    recurrencia = (recurrencia or "ninguna").strip().lower()
    if recurrencia not in _RECURRENCIAS:
        raise ValueError(
            "recurrencia no valida: usa ninguna, diaria, semanal o mensual."
        )
    dt = parse_datetime(cuando, future=True)
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO reminders (texto, cuando, canal, recurrencia) "
            "VALUES (?, ?, ?, ?)",
            (str(texto).strip(), dt.isoformat(), canal, recurrencia),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    finally:
        conn.close()
    return _row(row)


def listar_recordatorios(estado: str = "pendientes", limite: int = 50) -> dict:
    estado = (estado or "pendientes").strip().lower()
    if estado not in _ESTADO_FILTRO:
        raise ValueError(
            "estado no valido: usa pendientes, enviados, cancelados o todos"
        )
    filtro = _ESTADO_FILTRO[estado]
    conn = _conn()
    try:
        if filtro:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE estado = ? ORDER BY cuando LIMIT ?",
                (filtro, int(limite)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders ORDER BY cuando LIMIT ?", (int(limite),)
            ).fetchall()
    finally:
        conn.close()
    return {"total": len(rows), "recordatorios": [_row(r) for r in rows]}


def cancelar_recordatorio(id: int) -> dict:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (int(id),)
        ).fetchone()
        if row is None:
            raise ValueError(f"no existe ningun recordatorio con id {id}")
        if row["estado"] == "pendiente":
            conn.execute(
                "UPDATE reminders SET estado = 'cancelado' WHERE id = ?", (row["id"],)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (row["id"],)
            ).fetchone()
    finally:
        conn.close()
    return _row(row)


# --- helpers usados por el scheduler ---
def vencidos(ahora_iso: str | None = None) -> list[dict]:
    ahora = ahora_iso or datetime.now().isoformat()
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT * FROM reminders
               WHERE estado = 'pendiente' AND cuando <= ?
               ORDER BY cuando""",
            (ahora,),
        ).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def marcar_enviado(id: int) -> None:
    conn = _conn()
    try:
        conn.execute(
            """UPDATE reminders
               SET estado = 'enviado', enviado_en = datetime('now')
               WHERE id = ?""",
            (int(id),),
        )
        conn.commit()
    finally:
        conn.close()


def marcar_error(id: int) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE reminders SET estado = 'error' WHERE id = ?", (int(id),)
        )
        conn.commit()
    finally:
        conn.close()


def siguiente_ocurrencia(cuando: str, recurrencia: str | None) -> str | None:
    """Proxima fecha ISO para un recordatorio recurrente, o None si no recurre."""
    rec = (recurrencia or "ninguna").strip().lower()
    if rec in ("", "ninguna"):
        return None
    dt = parse_datetime(cuando)
    if rec == "diaria":
        return (dt + relativedelta(days=1)).isoformat()
    if rec == "semanal":
        return (dt + relativedelta(weeks=1)).isoformat()
    if rec == "mensual":
        return (dt + relativedelta(months=1)).isoformat()
    return None


def reprogramar(id: int, cuando: str) -> dict:
    """Reinicia un recordatorio recurrente a 'pendiente' con la nueva fecha."""
    conn = _conn()
    try:
        conn.execute(
            "UPDATE reminders SET estado = 'pendiente', cuando = ?, enviado_en = NULL "
            "WHERE id = ?",
            (parse_datetime(cuando).isoformat(), int(id)),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (int(id),)
        ).fetchone()
    finally:
        conn.close()
    return _row(row)
