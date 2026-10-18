"""Herramientas de recordatorios (persistidos en SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from dateutil.relativedelta import relativedelta

from ..config import settings
from ..db import connect
from ..timeutil import faltan_texto, parse_datetime, resolver_periodo
from ._tags import filtro_params, filtro_sql, lista as tags_lista, normalizar as tags_norm

_CANALES = {"windows", "telegram"}
_RECURRENCIAS = {"ninguna", "diaria", "semanal", "mensual"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    texto     TEXT NOT NULL,
    cuando    TEXT NOT NULL,
    canal     TEXT NOT NULL DEFAULT 'windows',
    recurrencia TEXT NOT NULL DEFAULT 'ninguna',
    etiquetas TEXT,
    estado    TEXT NOT NULL DEFAULT 'pendiente',
    creado_en TEXT NOT NULL DEFAULT (datetime('now')),
    enviado_en TEXT
);
"""

_ESTADO_FILTRO = {
    "pendientes": ("pendiente",),
    "pendiente": ("pendiente",),
    "enviados": ("enviado",),
    "enviado": ("enviado",),
    "cancelados": ("cancelado",),
    "cancelado": ("cancelado",),
    "historial": ("pendiente", "enviado"),
    "historiales": ("pendiente", "enviado"),
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
    if "etiquetas" not in cols:
        conn.execute("ALTER TABLE reminders ADD COLUMN etiquetas TEXT")
        conn.commit()
    return conn


def _row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["etiquetas"] = tags_lista(d.get("etiquetas"))
    return d


def crear_recordatorio(
    texto: str,
    cuando: str,
    canal: str = "windows",
    recurrencia: str = "ninguna",
    etiquetas=None,
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
            "INSERT INTO reminders (texto, cuando, canal, recurrencia, etiquetas) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(texto).strip(), dt.isoformat(), canal, recurrencia, tags_norm(etiquetas)),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    finally:
        conn.close()
    return _row(row)


def listar_recordatorios(
    estado: str = "pendientes",
    limite: int = 50,
    vencidos: bool = False,
    periodo: str | None = None,
    dias: int | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    etiqueta: str | None = None,
) -> dict:
    estado = (estado or "pendientes").strip().lower()
    if estado not in _ESTADO_FILTRO:
        raise ValueError(
            "estado no valido: usa pendientes, enviados, cancelados, "
            "historial o todos"
        )
    filtro = _ESTADO_FILTRO[estado]
    conds: list[str] = []
    params: list = []
    if filtro:
        placeholders = ", ".join("?" for _ in filtro)
        conds.append(f"estado IN ({placeholders})")
        params.extend(filtro)
    if etiqueta:
        conds.append(filtro_sql("etiquetas"))
        params.extend(filtro_params(etiqueta))
    if periodo:
        d, h = resolver_periodo(periodo, dias)
        conds.append("datetime(cuando) >= datetime(?)")
        params.append(d.isoformat())
        conds.append("datetime(cuando) <= datetime(?)")
        params.append(h.isoformat())
    else:
        if desde:
            conds.append("datetime(cuando) >= datetime(?)")
            params.append(parse_datetime(desde).isoformat())
        if hasta:
            conds.append("datetime(cuando) <= datetime(?)")
            params.append(parse_datetime(hasta, end_of_day=True).isoformat())
        if vencidos:
            conds.append("datetime(cuando) < datetime('now', 'localtime')")
    clause = ("WHERE " + " AND ".join(conds)) if conds else ""
    conn = _conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM reminders {clause} ORDER BY cuando LIMIT ?",
            (*params, int(limite)),
        ).fetchall()
    finally:
        conn.close()
    ahora = datetime.now()
    recs: list[dict] = []
    for r in rows:
        base = _row(r)
        d = {
            k: base[k]
            for k in ("id", "texto", "cuando", "canal", "recurrencia", "estado", "etiquetas")
        }
        try:
            d["faltan"] = faltan_texto(datetime.fromisoformat(d["cuando"]), ahora)
        except (ValueError, TypeError):
            d["faltan"] = None
        recs.append(d)
    return {"total": len(recs), "recordatorios": recs}


def obtener_recordatorio(id: int) -> dict | None:
    """Devuelve un recordatorio por id (o None). Para describir propuestas."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (int(id),)
        ).fetchone()
    finally:
        conn.close()
    return _row(row) if row is not None else None


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
