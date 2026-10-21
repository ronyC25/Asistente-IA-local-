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

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    canal          TEXT NOT NULL DEFAULT 'cli',
    resumen        TEXT,
    resumen_hasta  INTEGER NOT NULL DEFAULT 0,
    pending        TEXT,
    ultimos_eventos TEXT,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    rol        TEXT NOT NULL,
    contenido  TEXT,
    creado_en  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS memories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    clave          TEXT,
    valor          TEXT NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executescript(MEMORY_SCHEMA)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()
