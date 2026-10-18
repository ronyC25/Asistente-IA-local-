"""Herramientas de notas (texto libre) sobre SQLite.

Agrupadas en dos: ``consultar_notas`` (lectura) y ``gestionar_notas`` (escritura,
requiere confirmacion).
"""
from __future__ import annotations

import sqlite3

from ..config import settings
from ..db import connect
from ..timeutil import parse_datetime, resolver_periodo
from ._tags import filtro_params, filtro_sql, lista as tags_lista, normalizar as tags_norm

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo         TEXT,
    contenido      TEXT NOT NULL,
    etiquetas      TEXT,
    creada_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizada_en TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
    if "etiquetas" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN etiquetas TEXT")
        conn.commit()
    return conn


def _row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["etiquetas"] = tags_lista(d.get("etiquetas"))
    return d


def consultar_notas(
    accion: str = "listar",
    texto: str | None = None,
    limite: int = 20,
    periodo: str | None = None,
    dias: int | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    orden: str = "recientes",
    etiqueta: str | None = None,
) -> dict:
    """Lee notas. accion: 'listar' o 'buscar' (por 'texto').

    Filtra por fecha de creacion (``creada_en``) con ``periodo``/``dias`` o
    ``desde``/``hasta``; ``orden`` = 'recientes' (por defecto) o 'antiguas';
    ``etiqueta`` filtra por etiqueta exacta.
    """
    accion = (accion or "listar").strip().lower()
    limite = max(1, int(limite or 20))
    orden = (orden or "recientes").strip().lower()
    conn = _conn()
    try:
        if accion in ("listar", "todas", "recientes", "buscar", "busca", "encontrar"):
            where: list[str] = []
            params: list = []
            if accion in ("buscar", "busca", "encontrar"):
                if not texto or not str(texto).strip():
                    raise ValueError("para buscar notas indica 'texto'.")
                patron = f"%{str(texto).strip()}%"
                where.append("(titulo LIKE ? OR contenido LIKE ?)")
                params.extend([patron, patron])
            if etiqueta:
                where.append(filtro_sql("etiquetas"))
                params.extend(filtro_params(etiqueta))
            if periodo:
                d, h = resolver_periodo(periodo, dias)
                where.append("date(creada_en, 'localtime') >= date(?)")
                params.append(d.date().isoformat())
                where.append("date(creada_en, 'localtime') <= date(?)")
                params.append(h.date().isoformat())
            else:
                if desde:
                    where.append("date(creada_en, 'localtime') >= date(?)")
                    params.append(parse_datetime(desde).date().isoformat())
                if hasta:
                    where.append("date(creada_en, 'localtime') <= date(?)")
                    params.append(parse_datetime(hasta).date().isoformat())
            clause = ("WHERE " + " AND ".join(where)) if where else ""
            direction = "ASC" if orden in ("antiguas", "antigua", "asc") else "DESC"
            rows = conn.execute(
                f"""SELECT * FROM notes {clause}
                    ORDER BY creada_en {direction}, id {direction} LIMIT ?""",
                (*params, limite),
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
    etiquetas=None,
) -> dict:
    """Modifica notas. accion: 'crear', 'editar' o 'eliminar'."""
    accion = (accion or "").strip().lower()
    conn = _conn()
    try:
        if accion in ("crear", "anadir", "agregar", "nueva"):
            if not contenido or not str(contenido).strip():
                raise ValueError("la nota necesita 'contenido'.")
            cur = conn.execute(
                "INSERT INTO notes (titulo, contenido, etiquetas) VALUES (?, ?, ?)",
                (
                    (str(titulo).strip() if titulo else None),
                    str(contenido).strip(),
                    tags_norm(etiquetas),
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
            if etiquetas is not None:
                sets.append("etiquetas = ?")
                params.append(tags_norm(etiquetas))
            if not sets:
                raise ValueError("no indicaste que cambiar (titulo, contenido o etiquetas).")
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
