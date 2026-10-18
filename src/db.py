"""Capa de acceso a SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo        TEXT NOT NULL,
    descripcion   TEXT,
    prioridad     TEXT NOT NULL DEFAULT 'media',
    estado        TEXT NOT NULL DEFAULT 'pendiente',
    fecha_limite  TEXT,
    etiquetas     TEXT,
    parent_id     INTEGER,
    creada_en     TEXT NOT NULL DEFAULT (datetime('now')),
    completada_en TEXT,
    actualizada_en TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
