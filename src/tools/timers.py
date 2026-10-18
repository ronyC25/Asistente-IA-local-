"""Temporizadores y Pomodoro (persistidos en SQLite).

Se apoyan en el scheduler (``check_due``) para avisar al vencer. Los avisos se
envian por Telegram y/o al avatar conectado (voz), segun ``settings.pomodoro``.
Soporta varios temporizadores a la vez, pausa/reanudar y parametros de pomodoro
por temporizador.
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
    creado_en    TEXT NOT NULL DEFAULT (datetime('now')),
    restante_seg INTEGER,
    trabajo_min  INTEGER,
    descanso_min INTEGER,
    descanso_largo_min INTEGER,
    ciclos       INTEGER
);
"""

_COLUMNS = {
    "restante_seg": "INTEGER",
    "trabajo_min": "INTEGER",
    "descanso_min": "INTEGER",
    "descanso_largo_min": "INTEGER",
    "ciclos": "INTEGER",
}

_INICIAR = {"iniciar", "empezar", "crear", "nueva", "nuevo", "start", "comenzar", "lanzar"}
_CANCELAR = {"cancelar", "parar", "detener", "terminar", "stop", "cancela"}
_PAUSAR = {"pausar", "pausa", "pausalo"}
_REANUDAR = {"reanudar", "reanuda", "continuar", "continua", "resume", "reanudalo"}

_EN_CURSO = "estado IN ('activo', 'pausado')"


def _conn() -> sqlite3.Connection:
    conn = connect(settings.database)
    conn.execute(_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(timers)")}
    for name, decl in _COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE timers ADD COLUMN {name} {decl}")
    conn.commit()
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


def _params(t: dict) -> dict:
    """Parametros de pomodoro del timer (con respaldo en la config global)."""
    cfg = _cfg()
    return {
        "trabajo_min": t.get("trabajo_min") or cfg["trabajo_min"],
        "descanso_min": t.get("descanso_min") or cfg["descanso_min"],
        "descanso_largo_min": t.get("descanso_largo_min") or cfg["descanso_largo_min"],
        "ciclos": t.get("ciclos") or cfg["ciclos"],
    }


def _norm_tipo(tipo: str | None) -> str:
    t = (tipo or "temporizador").strip().lower()
    if t in ("pomodoro", "pomodoros"):
        return "pomodoro"
    if t in ("temporizador", "temporizadores", "timer", "cronometro", "cronometros"):
        return "temporizador"
    raise ValueError("tipo no valido: usa temporizador o pomodoro.")


def iniciar(
    minutos: int | None = None,
    etiqueta: str | None = None,
    tipo: str = "temporizador",
    trabajo_min: int | None = None,
    descanso_min: int | None = None,
    descanso_largo_min: int | None = None,
    ciclos: int | None = None,
) -> dict:
    """Inicia un temporizador o un pomodoro (puede haber varios a la vez)."""
    tipo = _norm_tipo(tipo)
    etq = str(etiqueta).strip() if etiqueta and str(etiqueta).strip() else None
    if tipo == "pomodoro":
        cfg = _cfg()
        params = {
            "trabajo_min": int(trabajo_min) if trabajo_min else cfg["trabajo_min"],
            "descanso_min": int(descanso_min) if descanso_min else cfg["descanso_min"],
            "descanso_largo_min": int(descanso_largo_min)
            if descanso_largo_min
            else cfg["descanso_largo_min"],
            "ciclos": int(ciclos) if ciclos else cfg["ciclos"],
        }
        mins = int(minutos) if minutos else params["trabajo_min"]
        fase, ciclo = "trabajo", 1
    else:
        if not minutos or int(minutos) <= 0:
            raise ValueError("indica los minutos del temporizador (p. ej. 10).")
        mins = int(minutos)
        fase, ciclo = "trabajo", 0
        params = {
            "trabajo_min": None,
            "descanso_min": None,
            "descanso_largo_min": None,
            "ciclos": None,
        }
    fin = datetime.now() + timedelta(minutes=mins)
    conn = _conn()
    try:
        cur = conn.execute(
            """INSERT INTO timers
               (tipo, etiqueta, fase, fin, duracion_min, ciclo,
                trabajo_min, descanso_min, descanso_largo_min, ciclos)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tipo,
                etq,
                fase,
                fin.isoformat(timespec="seconds"),
                mins,
                ciclo,
                params["trabajo_min"],
                params["descanso_min"],
                params["descanso_largo_min"],
                params["ciclos"],
            ),
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
    if estado in ("activos", "activo", "en_curso"):
        cond = _EN_CURSO
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
        rows = conn.execute(f"SELECT * FROM timers WHERE {cond} ORDER BY fin").fetchall()
    finally:
        conn.close()
    ahora = datetime.now()
    timers: list[dict] = []
    for r in rows:
        d = _row(r)
        d["faltan"] = None
        if d["estado"] == "activo":
            try:
                d["faltan"] = faltan_texto(datetime.fromisoformat(d["fin"]), ahora)
            except (ValueError, TypeError):
                pass
        timers.append(d)
    return {"total": len(timers), "temporizadores": timers}


def estado() -> dict:
    """Temporizadores/pomodoros activos o pausados (con cuanto falta)."""
    return listar("activos")


def obtener(id: int) -> dict | None:
    """Devuelve un temporizador por id (o None)."""
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (int(id),)).fetchone()
    finally:
        conn.close()
    return _row(row) if row is not None else None


def _resolver(
    conn: sqlite3.Connection, id: int | None, etiqueta: str | None
) -> sqlite3.Row:
    if id is not None:
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (int(id),)).fetchone()
        if row is None:
            raise ValueError(f"no existe ningun temporizador con id {id}")
        return row
    if etiqueta:
        rows = conn.execute(
            f"SELECT * FROM timers WHERE {_EN_CURSO} AND etiqueta LIKE ?",
            (f"%{str(etiqueta).strip()}%",),
        ).fetchall()
        if not rows:
            raise ValueError(
                f"no hay ningun temporizador activo con etiqueta {etiqueta!r}"
            )
        if len(rows) > 1:
            ids = ", ".join(str(r["id"]) for r in rows)
            raise ValueError(f"hay varios temporizadores con esa etiqueta (ids: {ids}).")
        return rows[0]
    rows = conn.execute(f"SELECT * FROM timers WHERE {_EN_CURSO} ORDER BY fin").fetchall()
    if not rows:
        raise ValueError("no hay ningun temporizador activo.")
    if len(rows) > 1:
        raise ValueError("hay varios temporizadores activos; indica el id o la etiqueta.")
    return rows[0]


def cancelar(id: int | None = None, etiqueta: str | None = None) -> dict:
    conn = _conn()
    try:
        row = _resolver(conn, id, etiqueta)
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


def pausar(id: int | None = None, etiqueta: str | None = None) -> dict:
    conn = _conn()
    try:
        row = _resolver(conn, id, etiqueta)
        if row["estado"] == "pausado":
            return _row(row)
        restante = max(
            0, int((datetime.fromisoformat(row["fin"]) - datetime.now()).total_seconds())
        )
        conn.execute(
            "UPDATE timers SET estado = 'pausado', restante_seg = ? WHERE id = ?",
            (restante, row["id"]),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    return _row(row)


def reanudar(id: int | None = None, etiqueta: str | None = None) -> dict:
    conn = _conn()
    try:
        row = _resolver(conn, id, etiqueta)
        if row["estado"] == "activo":
            return _row(row)
        fin = datetime.now() + timedelta(seconds=int(row["restante_seg"] or 0))
        conn.execute(
            "UPDATE timers SET estado = 'activo', fin = ?, restante_seg = NULL WHERE id = ?",
            (fin.isoformat(timespec="seconds"), row["id"]),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()
    return _row(row)


def gestionar(
    accion: str,
    tipo: str | None = None,
    minutos: int | None = None,
    etiqueta: str | None = None,
    id: int | None = None,
    trabajo_min: int | None = None,
    descanso_min: int | None = None,
    descanso_largo_min: int | None = None,
    ciclos: int | None = None,
) -> dict:
    """Dispatcher de la herramienta: iniciar | cancelar | pausar | reanudar."""
    a = (accion or "").strip().lower()
    if a in _INICIAR:
        return iniciar(
            minutos=minutos,
            etiqueta=etiqueta,
            tipo=tipo or "temporizador",
            trabajo_min=trabajo_min,
            descanso_min=descanso_min,
            descanso_largo_min=descanso_largo_min,
            ciclos=ciclos,
        )
    if a in _CANCELAR:
        return cancelar(id=id, etiqueta=etiqueta)
    if a in _PAUSAR:
        return pausar(id=id, etiqueta=etiqueta)
    if a in _REANUDAR:
        return reanudar(id=id, etiqueta=etiqueta)
    raise ValueError("accion no valida: usa iniciar, cancelar, pausar o reanudar.")


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


def avanzar(id: int, fin_esperado: str | None = None) -> bool:
    """Avanza la fase (pomodoro) o completa (temporizador) de forma ATOMICA.

    Devuelve True solo si este proceso lo reclamo (evita doble aviso con varios
    schedulers). ``fin_esperado`` es el ``fin`` leido; si otro proceso ya lo
    cambio, el UPDATE no afecta filas y se devuelve False.
    """
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (int(id),)).fetchone()
        if row is None:
            return False
        guard = "estado = 'activo'"
        extra: tuple = ()
        if fin_esperado:
            guard += " AND fin = ?"
            extra = (fin_esperado,)
        if row["tipo"] != "pomodoro":
            cur = conn.execute(
                f"UPDATE timers SET estado = 'completado' WHERE id = ? AND {guard}",
                (int(id), *extra),
            )
            conn.commit()
            return cur.rowcount == 1
        p = _params(_row(row))
        fase = row["fase"]
        ciclo = int(row["ciclo"])
        if fase == "trabajo":
            if p["ciclos"] > 0 and ciclo % p["ciclos"] == 0:
                nueva, mins = "descanso_largo", p["descanso_largo_min"]
            else:
                nueva, mins = "descanso", p["descanso_min"]
            nuevo_ciclo = ciclo
        else:
            nueva, mins = "trabajo", p["trabajo_min"]
            nuevo_ciclo = ciclo + 1
        fin = datetime.now() + timedelta(minutes=mins)
        cur = conn.execute(
            f"""UPDATE timers SET fase = ?, fin = ?, duracion_min = ?, ciclo = ?
                WHERE id = ? AND {guard}""",
            (nueva, fin.isoformat(timespec="seconds"), mins, nuevo_ciclo, int(id), *extra),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def mensaje_aviso(t: dict) -> str:
    """Texto del aviso segun el tipo y la fase que acaba de terminar."""
    p = _params(t)
    etq = t.get("etiqueta")
    suf = f" «{etq}»" if etq else ""
    if t.get("tipo") == "pomodoro":
        fase = t.get("fase")
        ciclo = int(t.get("ciclo") or 1)
        if fase == "trabajo":
            if p["ciclos"] > 0 and ciclo % p["ciclos"] == 0:
                prox, nombre = p["descanso_largo_min"], "descanso largo"
            else:
                prox, nombre = p["descanso_min"], "descanso"
            return (
                f"Pomodoro{suf}: trabajo del ciclo {ciclo} cumplido. "
                f"Toma un {nombre} de {prox} min."
            )
        return f"Pomodoro{suf}: descanso terminado. A trabajar (ciclo {ciclo + 1})."
    return f"Temporizador{suf}: tiempo cumplido."
