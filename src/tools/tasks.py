"""Herramientas de gestion de tareas (CRUD sobre SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

from ..config import settings
from ..db import connect
from ..timeutil import parse_datetime

_PRIORIDADES = {
    "alta": "alta",
    "media": "media",
    "baja": "baja",
    "high": "alta",
    "medium": "media",
    "low": "baja",
    "urgente": "alta",
}

_ESTADOS = {"pendiente", "completada"}


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo        TEXT NOT NULL,
            descripcion   TEXT,
            prioridad     TEXT NOT NULL DEFAULT 'media',
            estado        TEXT NOT NULL DEFAULT 'pendiente',
            fecha_limite  TEXT,
            creada_en     TEXT NOT NULL DEFAULT (datetime('now')),
            completada_en TEXT,
            actualizada_en TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    return conn


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def _norm_prioridad(p: str | None) -> str | None:
    if p is None:
        return None
    key = str(p).strip().lower()
    if key not in _PRIORIDADES:
        raise ValueError(
            f"prioridad no valida: {p!r}. Usa alta, media o baja."
        )
    return _PRIORIDADES[key]


def _norm_fecha(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    return parse_datetime(v).isoformat()


def _find(conn: sqlite3.Connection, id: int | None, titulo: str | None) -> sqlite3.Row:
    if id is not None:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(id),)).fetchone()
        if row is not None:
            return row
        raise ValueError(f"no existe ninguna tarea con id {id}")
    if titulo:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE titulo LIKE ? ORDER BY id DESC",
            (f"%{titulo}%",),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]
        if not rows:
            raise ValueError(f"no encontre ninguna tarea que coincida con {titulo!r}")
        ids = ", ".join(str(r["id"]) for r in rows)
        raise ValueError(
            f"hay varias tareas que coinciden con {titulo!r} (ids: {ids}). "
            "Especifica el id."
        )
    raise ValueError("debes indicar el id o el titulo de la tarea")


def crear_tarea(
    titulo: str,
    descripcion: str | None = None,
    prioridad: str | None = "media",
    fecha_limite: str | None = None,
) -> dict:
    if not titulo or not str(titulo).strip():
        raise ValueError("el titulo de la tarea no puede estar vacio")
    prio = _norm_prioridad(prioridad) or "media"
    fecha = _norm_fecha(fecha_limite)
    conn = _conn()
    try:
        cur = conn.execute(
            """INSERT INTO tasks (titulo, descripcion, prioridad, estado, fecha_limite)
               VALUES (?, ?, ?, 'pendiente', ?)""",
            (str(titulo).strip(), descripcion, prio, fecha),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()
    return _row(row)


def listar_tareas(
    estado: str = "pendientes",
    prioridad: str | None = None,
    vencen_hoy: bool = False,
    vencidas: bool = False,
    limite: int = 50,
) -> dict:
    estado = (estado or "pendientes").strip().lower()
    where: list[str] = []
    params: list = []
    if estado in ("pendientes", "pendiente"):
        where.append("estado = 'pendiente'")
    elif estado in ("completadas", "completada"):
        where.append("estado = 'completada'")
    elif estado in ("todas", "todo", "todos"):
        pass
    else:
        raise ValueError("estado no valido: usa pendientes, completadas o todas")
    if prioridad:
        where.append("prioridad = ?")
        params.append(_norm_prioridad(prioridad))
    if vencen_hoy:
        where.append("date(fecha_limite) = date('now', 'localtime')")
    if vencidas:
        where.append(
            "fecha_limite IS NOT NULL AND "
            "datetime(fecha_limite) < datetime('now', 'localtime')"
        )
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    conn = _conn()
    try:
        rows = conn.execute(
            f"""SELECT * FROM tasks {clause}
                ORDER BY (fecha_limite IS NULL), fecha_limite, id DESC
                LIMIT ?""",
            (*params, int(limite)),
        ).fetchall()
    finally:
        conn.close()
    return {"total": len(rows), "tareas": [_row(r) for r in rows]}


def obtener_tarea(id: int) -> dict | None:
    """Devuelve una tarea por id (o None si no existe). Para describir propuestas."""
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(id),)).fetchone()
    finally:
        conn.close()
    return _row(row) if row is not None else None


def completar_tarea(id: int | None = None, titulo: str | None = None) -> dict:
    conn = _conn()
    try:
        row = _find(conn, id, titulo)
        if row["estado"] == "completada":
            return _row(row)
        conn.execute(
            """UPDATE tasks
               SET estado = 'completada',
                   completada_en = datetime('now'),
                   actualizada_en = datetime('now')
               WHERE id = ?""",
            (row["id"],),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    return _row(row)


def editar_tarea(
    id: int | None = None,
    titulo: str | None = None,
    nuevo_titulo: str | None = None,
    descripcion: str | None = None,
    prioridad: str | None = None,
    fecha_limite: str | None = None,
    estado: str | None = None,
) -> dict:
    conn = _conn()
    try:
        row = _find(conn, id, titulo)
        sets: list[str] = []
        params: list = []
        if nuevo_titulo:
            sets.append("titulo = ?")
            params.append(str(nuevo_titulo).strip())
        if descripcion is not None:
            sets.append("descripcion = ?")
            params.append(descripcion)
        if prioridad is not None:
            sets.append("prioridad = ?")
            params.append(_norm_prioridad(prioridad))
        if fecha_limite is not None:
            sets.append("fecha_limite = ?")
            params.append(_norm_fecha(fecha_limite))
        if estado is not None:
            est = str(estado).strip().lower()
            if est not in _ESTADOS:
                raise ValueError("estado no valido: usa pendiente o completada")
            sets.append("estado = ?")
            params.append(est)
        if not sets:
            return _row(row)
        sets.append("actualizada_en = datetime('now')")
        params.append(row["id"])
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    return _row(row)


def eliminar_tarea(id: int | None = None, titulo: str | None = None) -> dict:
    conn = _conn()
    try:
        row = _find(conn, id, titulo)
        conn.execute("DELETE FROM tasks WHERE id = ?", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    return {"eliminada": True, "id": row["id"], "titulo": row["titulo"]}


def fecha_hora_actual() -> dict:
    now = datetime.now()
    dias = [
        "lunes",
        "martes",
        "miercoles",
        "jueves",
        "viernes",
        "sabado",
        "domingo",
    ]
    return {
        "iso": now.isoformat(timespec="minutes"),
        "fecha": now.date().isoformat(),
        "hora": now.strftime("%H:%M"),
        "dia_semana": dias[now.weekday()],
        "hoy_es": date.today().isoformat(),
    }
