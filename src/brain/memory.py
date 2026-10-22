"""Memoria persistente: sesiones, mensajes duraderos, resumen y hechos.

Se guarda en la misma SQLite que el resto de datos. Las conversaciones son por
sesion/canal; los hechos (``recuerda que ...``) son globales y se comparten
entre web, Telegram, CLI, voz y avatar.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from ..db import connect, init_db

_RE_RECUERDA = re.compile(
    r"^\s*(?:recuerda\s+que|ten en cuenta que|guarda(?: en memoria)?(?:\s+que)?)"
    r"\s+(.+)$",
    re.IGNORECASE,
)
_RE_OLVIDA = re.compile(
    r"^\s*(?:/olvida|olvida(?:te)?(?:\s+de)?|borra(?: de memoria)?)"
    r"\s+(.+)$",
    re.IGNORECASE,
)
_COMANDOS_MEMORIA = {
    "/memoria",
    "/memorias",
    "/recuerdos",
    "/olvida",
    "memoria",
    "que recuerdas",
    "que sabes de mi",
    "mis recuerdos",
}


def hecho_de_texto(text: str) -> str | None:
    """Extrae un hecho de 'recuerda que ...' (no de 'recuerdame ...')."""
    m = _RE_RECUERDA.match(text or "")
    if not m:
        return None
    hecho = " ".join(m.group(1).split()).strip()
    return hecho if len(hecho) >= 3 else None


def olvido_de_texto(text: str) -> str | None:
    """Extrae el texto a olvidar de '/olvida ...' o 'olvida ...'."""
    m = _RE_OLVIDA.match(text or "")
    if not m:
        return None
    valor = " ".join(m.group(1).split()).strip()
    valor = re.sub(r"^que\s+", "", valor, flags=re.IGNORECASE).strip()
    return valor or None


def es_comando_memoria(text: str) -> bool:
    t = " ".join((text or "").strip().lower().split())
    if t.endswith("@") or "@" in t:
        t = t.split("@")[0].strip()
    return t in _COMANDOS_MEMORIA


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


class SessionStore:
    """Acceso a las tablas de memoria (sessions, messages, memories)."""

    def __init__(self, db_path: str, keep_messages: int = 500) -> None:
        self.db_path = db_path
        self.keep_messages = max(50, int(keep_messages))
        init_db(db_path)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def _ensure_session(
        self, conn: sqlite3.Connection, session_id: str, canal: str
    ) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, canal) VALUES (?, ?)",
            (session_id, canal),
        )

    # ------------------------------------------------------------ sesiones
    def load(self, session_id: str, canal: str = "cli", limite: int = 16) -> dict:
        """Carga resumen, estado pendiente y los ultimos mensajes duraderos."""
        conn = self._conn()
        try:
            self._ensure_session(conn, session_id, canal)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            mensajes = conn.execute(
                "SELECT rol, contenido FROM ("
                "  SELECT id, rol, contenido FROM messages "
                "  WHERE session_id = ? ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC",
                (session_id, int(limite)),
            ).fetchall()
        finally:
            conn.close()
        return {
            "id": session_id,
            "canal": row["canal"] if row is not None else canal,
            "resumen": row["resumen"] if row is not None else None,
            "resumen_hasta": int(row["resumen_hasta"]) if row is not None else 0,
            "pending": _loads(row["pending"] if row is not None else None, None),
            "ultimos_eventos": _loads(
                row["ultimos_eventos"] if row is not None else None, []
            ),
            "mensajes": [
                {"role": m["rol"], "content": m["contenido"] or ""} for m in mensajes
            ],
        }

    def save_turn(
        self,
        session_id: str,
        canal: str,
        user_text: str,
        reply: str | None,
        pending: list[tuple[str, dict]] | None,
        ultimos_eventos: list[dict] | None,
    ) -> None:
        """Guarda un turno (mensaje del usuario + respuesta) y el estado."""
        conn = self._conn()
        try:
            self._ensure_session(conn, session_id, canal)
            conn.execute(
                "INSERT INTO messages (session_id, rol, contenido) VALUES (?, 'user', ?)",
                (session_id, user_text),
            )
            if reply:
                conn.execute(
                    "INSERT INTO messages (session_id, rol, contenido) "
                    "VALUES (?, 'assistant', ?)",
                    (session_id, reply),
                )
            self._prune(conn, session_id)
            self._save_state_conn(conn, session_id, canal, pending, ultimos_eventos)
            conn.commit()
        finally:
            conn.close()

    def save_state(
        self,
        session_id: str,
        canal: str,
        pending: list[tuple[str, dict]] | None,
        ultimos_eventos: list[dict] | None,
    ) -> None:
        conn = self._conn()
        try:
            self._ensure_session(conn, session_id, canal)
            self._save_state_conn(conn, session_id, canal, pending, ultimos_eventos)
            conn.commit()
        finally:
            conn.close()

    def _prune(self, conn: sqlite3.Connection, session_id: str) -> None:
        """Conserva solo los ultimos ``keep_messages`` mensajes de la sesion."""
        if self.keep_messages <= 0:
            return
        row = conn.execute(
            "SELECT MAX(id) AS max_id FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        max_id = int(row["max_id"]) if row is not None and row["max_id"] else 0
        if not max_id:
            return
        conn.execute(
            "DELETE FROM messages WHERE session_id = ? AND id <= ?",
            (session_id, max_id - self.keep_messages),
        )

    @staticmethod
    def _save_state_conn(
        conn: sqlite3.Connection,
        session_id: str,
        canal: str,
        pending: list[tuple[str, dict]] | None,
        ultimos_eventos: list[dict] | None,
    ) -> None:
        conn.execute(
            "UPDATE sessions SET canal = ?, pending = ?, ultimos_eventos = ?, "
            "actualizado_en = datetime('now') WHERE id = ?",
            (
                canal,
                _dumps(pending),
                _dumps(ultimos_eventos or []),
                session_id,
            ),
        )

    def reset(self, session_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------ resumen
    def count_messages(self, session_id: str, despues_de: int = 0) -> int:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM messages "
                "WHERE session_id = ? AND id > ?",
                (session_id, int(despues_de)),
            ).fetchone()
            return int(row["n"])
        finally:
            conn.close()

    def mensajes_despues(self, session_id: str, despues_de: int) -> list[dict]:
        """Mensajes con id > despues_de, en orden cronologico (incluye id)."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, rol, contenido FROM messages "
                "WHERE session_id = ? AND id > ? ORDER BY id ASC",
                (session_id, int(despues_de)),
            ).fetchall()
        finally:
            conn.close()
        return [
            {"id": int(r["id"]), "rol": r["rol"], "contenido": r["contenido"] or ""}
            for r in rows
        ]

    def set_summary(
        self, session_id: str, resumen: str, resumen_hasta: int
    ) -> None:
        conn = self._conn()
        try:
            self._ensure_session(conn, session_id, "cli")
            conn.execute(
                "UPDATE sessions SET resumen = ?, resumen_hasta = ?, "
                "actualizado_en = datetime('now') WHERE id = ?",
                (resumen, int(resumen_hasta), session_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------- hechos
    def add_fact(self, valor: str, clave: str | None = None) -> dict:
        texto = " ".join(str(valor or "").split()).strip()
        if not texto:
            raise ValueError("el hecho no puede estar vacio")
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM memories WHERE lower(valor) = lower(?) "
                "ORDER BY id DESC LIMIT 1",
                (texto,),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE memories SET clave = COALESCE(?, clave), "
                    "actualizado_en = datetime('now') WHERE id = ?",
                    (clave, row["id"]),
                )
                conn.commit()
                ident = int(row["id"])
            else:
                cur = conn.execute(
                    "INSERT INTO memories (clave, valor) VALUES (?, ?)",
                    (clave, texto),
                )
                conn.commit()
                ident = int(cur.lastrowid)
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (ident,)
            ).fetchone()
            return {
                "id": int(row["id"]),
                "clave": row["clave"],
                "valor": row["valor"],
            }
        finally:
            conn.close()

    def list_facts(self, limite: int = 20) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM memories ORDER BY id DESC LIMIT ?) "
                "ORDER BY id ASC",
                (int(limite),),
            ).fetchall()
        finally:
            conn.close()
        return [
            {"id": int(r["id"]), "clave": r["clave"], "valor": r["valor"]}
            for r in rows
        ]

    def delete_fact(self, texto: str) -> int:
        patron = f"%{' '.join(str(texto or '').split())}%"
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM memories WHERE valor LIKE ? OR clave LIKE ?",
                (patron, patron),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    def clear_facts(self) -> int:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM memories")
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    def clear_summary(self, session_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE sessions SET resumen = NULL, resumen_hasta = 0, "
                "actualizado_en = datetime('now') WHERE id = ?",
                (session_id,),
            )
            conn.commit()
        finally:
            conn.close()
