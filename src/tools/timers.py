"""Temporizadores y Pomodoro (persistidos en SQLite).

Se apoyan en el scheduler (``check_due``) para avisar al vencer. Los avisos se
envian por Telegram y/o al avatar conectado (voz), segun ``settings.pomodoro``.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from ..config import settings
from ..db import connect
from ..timeutil import faltan_texto

_SCHEMA = """
CREATE TABLE IF NOT EXISTS timers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo         TEXT NOT NULL DEFAULT 'temporizador',
    etiqueta     TEXT,
    fase         TEXT NOT NULL DEFAULT 'trabajo',
    fin          TEXT NOT NULL,
    duracion_min INTEGER NOT NULL,
    ciclo        INTEGER NOT NULL DEFAULT 0,
    estado       TEXT NOT NULL DEFAULT 'activo',
    creado_en    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_INICIAR = {"iniciar", "empezar", "crear", "nueva", "nuevo", "start", "comenzar", "lanzar"}
_CANCELAR = {"cancelar", "parar", "detener", "terminar", "stop", "cancela"}


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(_SCHEMA)
    return conn


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def _cfg() -> dict:
    cfg = getattr(settings, "pomodoro", None) or {}
    return {
        "trabajo_min": int(cfg.get("trabajo_min", 25)),
        "descanso_min": int(cfg.get("descanso_min", 5)),
        "descanso_largo_min": int(cfg.get("descanso_largo_min", 15)),
        "ciclos": int(cfg.get("ciclos", 4)),
    }


def _norm_tipo(tipo: str | None) -> str:
    t = (tipo or "temporizador").strip().lower()
    if t in ("pomodoro", "pomodoros"):
        return "pomodoro"
    if t in ("temporizador", "temporizadores", "timer", "cronometro", "cronometros"):
        return "temporizador"
    raise ValueError("tipo no valido: usa temporizador o pomodoro.")


def iniciar(
    minutos: int | None = None, etiqueta: str | None = None, tipo: str = "temporizador"
) -> dict:
    """Inicia un temporizador o un pomodoro (puede haber varios a la vez)."""
    tipo = _norm_tipo(tipo)
    cfg = _cfg()
    if tipo == "pomodoro":
        mins = int(minutos) if minutos else cfg["trabajo_min"]
        fase = "trabajo"
        ciclo = 1
    else:
        if not minutos or int(minutos) <= 0:
            raise ValueError("indica los minutos del temporizador (p. ej. 10).")
        mins = int(minutos)
        fase = "trabajo"
        ciclo = 0
    fin = datetime.now() + timedelta(minutes=mins)
    etq = str(etiqueta).strip() if etiqueta and str(etiqueta).strip() else None
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO timers (tipo, etiqueta, fase, fin, duracion_min, ciclo) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tipo, etq, fase, fin.isoformat(timespec="seconds"), mins, ciclo),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM timers WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    finally:
        conn.close()
    return _row(row)


def listar(estado: str = "activos") -> dict:
    estado = (estado or "activos").strip().lower()
    if estado in ("activos", "activo"):
        cond = "estado = 'activo'"
    elif estado in ("todos", "todas"):
        cond = "1=1"
    elif estado in ("completados", "completado"):
        cond = "estado = 'completado'"
    elif estado in ("cancelados", "cancelado"):
        cond = "estado = 'cancelado'"
    else:
        raise ValueError("estado no valido: usa activos, completados o cancelados.")
    conn = _conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM timers WHERE {cond} ORDER BY fin"
        ).fetchall()
    finally:
        conn.close()
    ahora = datetime.now()
    timers: list[dict] = []
    for r in rows:
        d = _row(r)
        d["faltan"] = None
        try:
            d["faltan"] = faltan_texto(datetime.fromisoformat(d["fin"]), ahora)
        except (ValueError, TypeError):
            pass
        timers.append(d)
    return {"total": len(timers), "temporizadores": timers}


def estado() -> dict:
    """Temporizadores/pomodoros activos (con cuanto falta)."""
    return listar("activos")


def cancelar(id: int | None = None, etiqueta: str | None = None) -> dict:
    conn = _conn()
    try:
        if id is not None:
            row = conn.execute("SELECT * FROM timers WHERE id = ?", (int(id),)).fetchone()
            if row is None:
                raise ValueError(f"no existe ningun temporizador con id {id}")
        elif etiqueta:
            rows = conn.execute(
                "SELECT * FROM timers WHERE estado = 'activo' AND etiqueta LIKE ?",
                (f"%{str(etiqueta).strip()}%",),
            ).fetchall()
            if not rows:
                raise ValueError(
                    f"no hay ningun temporizador activo con etiqueta {etiqueta!r}"
                )
            if len(rows) > 1:
                ids = ", ".join(str(r["id"]) for r in rows)
                raise ValueError(
                    f"hay varios temporizadores con esa etiqueta (ids: {ids})."
                )
            row = rows[0]
        else:
            rows = conn.execute(
                "SELECT * FROM timers WHERE estado = 'activo' ORDER BY fin"
            ).fetchall()
            if not rows:
                raise ValueError("no hay ningun temporizador activo.")
            if len(rows) > 1:
                raise ValueError(
                    "hay varios temporizadores activos; indica el id o la etiqueta."
                )
            row = rows[0]
        if row["estado"] != "cancelado":
            conn.execute(
                "UPDATE timers SET estado = 'cancelado' WHERE id = ?", (row["id"],)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM timers WHERE id = ?", (row["id"],)
            ).fetchone()
    finally:
        conn.close()
    return _row(row)


def gestionar(
    accion: str,
    tipo: str | None = None,
    minutos: int | None = None,
    etiqueta: str | None = None,
    id: int | None = None,
) -> dict:
    """Dispatcher de la herramienta: accion 'iniciar' o 'cancelar'."""
    a = (accion or "").strip().lower()
    if a in _INICIAR:
        return iniciar(minutos=minutos, etiqueta=etiqueta, tipo=tipo or "temporizador")
    if a in _CANCELAR:
        return cancelar(id=id, etiqueta=etiqueta)
    raise ValueError("accion no valida: usa iniciar o cancelar.")


# --- helpers usados por el scheduler ---
def vencidos(ahora_iso: str | None = None) -> list[dict]:
    ahora = ahora_iso or datetime.now().isoformat()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM timers WHERE estado = 'activo' AND fin <= ? ORDER BY fin",
            (ahora,),
        ).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def marcar_completado(id: int) -> None:
    conn = _conn()
    try:
        conn.execute("UPDATE timers SET estado = 'completado' WHERE id = ?", (int(id),))
        conn.commit()
    finally:
        conn.close()


def avanzar(id: int) -> dict | None:
    """Avanza la fase de un pomodoro (trabajo<->descanso). None si se completa."""
    cfg = _cfg()
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (int(id),)).fetchone()
        if row is None:
            return None
        if row["tipo"] != "pomodoro":
            conn.execute("UPDATE timers SET estado = 'completado' WHERE id = ?", (int(id),))
            conn.commit()
            return None
        fase = row["fase"]
        ciclo = int(row["ciclo"])
        if fase == "trabajo":
            if cfg["ciclos"] > 0 and ciclo % cfg["ciclos"] == 0:
                nueva_fase = "descanso_largo"
                mins = cfg["descanso_largo_min"]
            else:
                nueva_fase = "descanso"
                mins = cfg["descanso_min"]
            nuevo_ciclo = ciclo
        else:
            nueva_fase = "trabajo"
            mins = cfg["trabajo_min"]
            nuevo_ciclo = ciclo + 1
        fin = datetime.now() + timedelta(minutes=mins)
        conn.execute(
            "UPDATE timers SET fase = ?, fin = ?, duracion_min = ?, ciclo = ? WHERE id = ?",
            (nueva_fase, fin.isoformat(timespec="seconds"), mins, nuevo_ciclo, int(id)),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (int(id),)).fetchone()
    finally:
        conn.close()
    return _row(row)


def mensaje_aviso(t: dict) -> str:
    """Texto del aviso segun el tipo y la fase que acaba de terminar."""
    cfg = _cfg()
    etq = t.get("etiqueta")
    suf = f" «{etq}»" if etq else ""
    if t.get("tipo") == "pomodoro":
        fase = t.get("fase")
        ciclo = int(t.get("ciclo") or 1)
        if fase == "trabajo":
            if cfg["ciclos"] > 0 and ciclo % cfg["ciclos"] == 0:
                prox, nombre = cfg["descanso_largo_min"], "descanso largo"
            else:
                prox, nombre = cfg["descanso_min"], "descanso"
            return (
                f"Pomodoro{suf}: trabajo del ciclo {ciclo} cumplido. "
                f"Toma un {nombre} de {prox} min."
            )
        return f"Pomodoro{suf}: descanso terminado. A trabajar (ciclo {ciclo + 1})."
    return f"Temporizador{suf}: tiempo cumplido."
