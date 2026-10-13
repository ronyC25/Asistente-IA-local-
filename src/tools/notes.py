"""Herramientas de notas (texto libre) sobre SQLite.

Agrupadas en dos: ``consultar_notas`` (lectura) y ``gestionar_notas`` (escritura,
requiere confirmacion).
"""
from __future__ import annotations

import sqlite3

from ..config import settings
from ..db import connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo         TEXT,
    contenido      TEXT NOT NULL,
    creada_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizada_en TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(_SCHEMA)
    return conn


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def consultar_notas(
    accion: str = "listar",
    texto: str | None = None,
    limite: int = 20,
) -> dict:
    """Lee notas. accion: 'listar' (recientes) o 'buscar' (por texto)."""
    accion = (accion or "listar").strip().lower()
    limite = max(1, int(limite or 20))
    conn = _conn()
    try:
        if accion in ("listar", "todas", "recientes"):
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY actualizada_en DESC, id DESC LIMIT ?",
                (limite,),
            ).fetchall()
        elif accion in ("buscar", "busca", "encontrar"):
            if not texto or not str(texto).strip():
                raise ValueError("para buscar notas indica 'texto'.")
            patron = f"%{str(texto).strip()}%"
            rows = conn.execute(
                """SELECT * FROM notes
                   WHERE titulo LIKE ? OR contenido LIKE ?
                   ORDER BY actualizada_en DESC, id DESC LIMIT ?""",
                (patron, patron, limite),
            ).fetchall()
        else:
            raise ValueError("accion no valida: usa listar o buscar.")
    finally:
        conn.close()
    return {"total": len(rows), "notas": [_row(r) for r in rows]}


def gestionar_notas(
    accion: str,
    id: int | None = None,
    titulo: str | None = None,
    contenido: str | None = None,
) -> dict:
    """Modifica notas. accion: 'crear', 'editar' o 'eliminar'."""
    accion = (accion or "").strip().lower()
    conn = _conn()
    try:
        if accion in ("crear", "anadir", "agregar", "nueva"):
            if not contenido or not str(contenido).strip():
                raise ValueError("la nota necesita 'contenido'.")
            cur = conn.execute(
                "INSERT INTO notes (titulo, contenido) VALUES (?, ?)",
                (
                    (str(titulo).strip() if titulo else None),
                    str(contenido).strip(),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return _row(row)

        if accion in ("editar", "actualizar", "modificar"):
            if id is None:
                raise ValueError("para editar una nota indica el 'id'.")
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (int(id),)
            ).fetchone()
            if row is None:
                raise ValueError(f"no existe ninguna nota con id {id}")
            sets: list[str] = []
            params: list = []
            if titulo is not None:
                sets.append("titulo = ?")
                params.append(str(titulo).strip() or None)
            if contenido is not None:
                sets.append("contenido = ?")
                params.append(str(contenido).strip())
            if not sets:
                raise ValueError("no indicaste que cambiar (titulo o contenido).")
            sets.append("actualizada_en = datetime('now')")
            params.append(int(id))
            conn.execute(f"UPDATE notes SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (int(id),)
            ).fetchone()
            return _row(row)

        if accion in ("eliminar", "borrar", "borra"):
            if id is None:
                raise ValueError("para eliminar una nota indica el 'id'.")
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (int(id),)
            ).fetchone()
            if row is None:
                raise ValueError(f"no existe ninguna nota con id {id}")
            conn.execute("DELETE FROM notes WHERE id = ?", (int(id),))
            conn.commit()
            return {"eliminada": True, "id": int(id), "titulo": row["titulo"]}

        raise ValueError("accion no valida: usa crear, editar o eliminar.")
    finally:
        conn.close()
