"""Herramientas de listas/checklists sobre SQLite.

Agrupadas en dos: ``consultar_listas`` (lectura) y ``gestionar_listas``
(escritura, requiere confirmacion).
"""
from __future__ import annotations

import sqlite3

from ..config import settings
from ..db import connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre         TEXT NOT NULL,
    creada_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizada_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS list_items (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id  INTEGER NOT NULL,
    texto    TEXT NOT NULL,
    hecho    INTEGER NOT NULL DEFAULT 0,
    creada_en TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (list_id) REFERENCES lists(id)
);
"""


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.executescript(_SCHEMA)
    return conn


def _find_lista(
    conn: sqlite3.Connection, id: int | None, nombre: str | None
) -> sqlite3.Row:
    if id is not None:
        row = conn.execute("SELECT * FROM lists WHERE id = ?", (int(id),)).fetchone()
        if row is not None:
            return row
        raise ValueError(f"no existe ninguna lista con id {id}")
    if nombre:
        rows = conn.execute(
            "SELECT * FROM lists WHERE nombre LIKE ? ORDER BY id DESC",
            (f"%{str(nombre).strip()}%",),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]
        if not rows:
            raise ValueError(f"no encontre ninguna lista que coincida con {nombre!r}")
        ids = ", ".join(str(r["id"]) for r in rows)
        raise ValueError(
            f"hay varias listas que coinciden con {nombre!r} (ids: {ids}). "
            "Especifica el id."
        )
    raise ValueError("indica la lista por 'id' o 'nombre'.")


def consultar_listas(
    accion: str = "listar",
    id: int | None = None,
    nombre: str | None = None,
) -> dict:
    """Lee listas. accion: 'listar' (todas) o 'ver' (items de una lista)."""
    accion = (accion or "listar").strip().lower()
    conn = _conn()
    try:
        if accion in ("listar", "todas"):
            rows = conn.execute(
                """SELECT l.*,
                       (SELECT COUNT(*) FROM list_items i WHERE i.list_id = l.id) AS total,
                       (SELECT COUNT(*) FROM list_items i
                          WHERE i.list_id = l.id AND i.hecho = 1) AS hechos
                   FROM lists l ORDER BY l.actualizada_en DESC, l.id DESC"""
            ).fetchall()
            listas = []
            for r in rows:
                d = dict(r)
                items = conn.execute(
                    "SELECT * FROM list_items WHERE list_id = ? ORDER BY hecho, id",
                    (r["id"],),
                ).fetchall()
                d["items"] = [dict(x) for x in items]
                listas.append(d)
            return {"total": len(listas), "listas": listas}

        if accion in ("ver", "items", "mostrar"):
            lista = _find_lista(conn, id, nombre)
            items = conn.execute(
                "SELECT * FROM list_items WHERE list_id = ? ORDER BY hecho, id",
                (lista["id"],),
            ).fetchall()
            return {
                "lista": dict(lista),
                "total": len(items),
                "items": [dict(r) for r in items],
            }

        raise ValueError("accion no valida: usa listar o ver.")
    finally:
        conn.close()


def gestionar_listas(
    accion: str,
    id: int | None = None,
    nombre: str | None = None,
    texto: str | None = None,
    item_id: int | None = None,
    hecho: bool = True,
    items: list | None = None,
) -> dict:
    """Modifica listas. accion: crear | agregar | marcar | desmarcar |
    eliminar_item | eliminar_lista. ``items`` permite crear/anadir varios de golpe."""
    accion = (accion or "").strip().lower()
    conn = _conn()
    try:
        if accion in ("crear", "nueva", "crea"):
            if not nombre or not str(nombre).strip():
                raise ValueError("la lista necesita un 'nombre'.")
            cur = conn.execute(
                "INSERT INTO lists (nombre) VALUES (?)", (str(nombre).strip(),)
            )
            list_id = cur.lastrowid
            for it in items or []:
                if str(it).strip():
                    conn.execute(
                        "INSERT INTO list_items (list_id, texto) VALUES (?, ?)",
                        (list_id, str(it).strip()),
                    )
            conn.commit()
            row = conn.execute("SELECT * FROM lists WHERE id = ?", (list_id,)).fetchone()
            d = dict(row)
            d["items"] = [
                dict(x)
                for x in conn.execute(
                    "SELECT * FROM list_items WHERE list_id = ? ORDER BY id",
                    (list_id,),
                ).fetchall()
            ]
            return d

        if accion in ("agregar", "anadir", "add"):
            lista = _find_lista(conn, id, nombre)
            textos = [str(texto).strip()] if texto and str(texto).strip() else []
            textos += [str(it).strip() for it in (items or []) if str(it).strip()]
            if not textos:
                raise ValueError("el item necesita 'texto' o 'items'.")
            for t in textos:
                conn.execute(
                    "INSERT INTO list_items (list_id, texto) VALUES (?, ?)",
                    (lista["id"], t),
                )
            conn.execute(
                "UPDATE lists SET actualizada_en = datetime('now') WHERE id = ?",
                (lista["id"],),
            )
            conn.commit()
            return {"lista": dict(lista), "agregados": textos}

        if accion in ("marcar", "desmarcar"):
            if item_id is None:
                raise ValueError("indica 'item_id' para marcar/desmarcar.")
            valor = 1 if (accion == "marcar" and hecho) else 0
            cur = conn.execute(
                "UPDATE list_items SET hecho = ? WHERE id = ?",
                (valor, int(item_id)),
            )
            if cur.rowcount == 0:
                raise ValueError(f"no existe ningun item con id {item_id}")
            conn.commit()
            row = conn.execute(
                "SELECT * FROM list_items WHERE id = ?", (int(item_id),)
            ).fetchone()
            return dict(row)

        if accion in ("eliminar_item", "borrar_item"):
            if item_id is None:
                raise ValueError("indica 'item_id' para eliminar el item.")
            cur = conn.execute("DELETE FROM list_items WHERE id = ?", (int(item_id),))
            if cur.rowcount == 0:
                raise ValueError(f"no existe ningun item con id {item_id}")
            conn.commit()
            return {"eliminado_item": True, "item_id": int(item_id)}

        if accion in ("eliminar_lista", "borrar_lista"):
            lista = _find_lista(conn, id, nombre)
            conn.execute("DELETE FROM list_items WHERE list_id = ?", (lista["id"],))
            conn.execute("DELETE FROM lists WHERE id = ?", (lista["id"],))
            conn.commit()
            return {"eliminada": True, "id": lista["id"], "nombre": lista["nombre"]}

        raise ValueError(
            "accion no valida: usa crear, agregar, marcar, desmarcar, "
            "eliminar_item o eliminar_lista."
        )
    finally:
        conn.close()
