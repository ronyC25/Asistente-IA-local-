"""Busqueda global en los datos locales y listado de etiquetas."""
from __future__ import annotations

from . import calendar, lists, notes, reminders, tasks
from ._tags import lista as tags_lista


def _patron(texto: str) -> str:
    return f"%{str(texto).strip()}%"


def _dominios(dominios) -> set[str] | None:
    if not dominios:
        return None
    if isinstance(dominios, str):
        return {d.strip().lower() for d in dominios.split(",") if d.strip()}
    return {str(d).strip().lower() for d in dominios}


def buscar_todo(texto: str, limite: int = 10, dominios=None) -> dict:
    """Busca 'texto' en tareas, notas, eventos, recordatorios y listas.

    Devuelve resultados agrupados por dominio (recortados a campos utiles) y
    ``total`` con la suma de coincidencias. ``dominios`` (opcional) restringe la
    busqueda a uno o varios dominios: tareas, notas, eventos, recordatorios, listas.
    """
    if not texto or not str(texto).strip():
        raise ValueError("indica el texto a buscar.")
    lim = max(1, int(limite or 10))
    pat = _patron(texto)
    dom = _dominios(dominios)

    def quiere(d: str) -> bool:
        return dom is None or d in dom

    res: dict = {"total": 0}
    total = 0

    if quiere("tareas"):
        conn = tasks._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE titulo LIKE ? OR descripcion LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (pat, pat, lim),
            ).fetchall()
        finally:
            conn.close()
        items = []
        for r in rows:
            b = tasks._row(r)
            items.append(
                {
                    "id": b["id"],
                    "titulo": b["titulo"],
                    "estado": b["estado"],
                    "prioridad": b["prioridad"],
                    "fecha_limite": b["fecha_limite"],
                    "etiquetas": b["etiquetas"],
                }
            )
        res["tareas"] = items
        total += len(items)

    if quiere("notas"):
        conn = notes._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM notes WHERE titulo LIKE ? OR contenido LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (pat, pat, lim),
            ).fetchall()
        finally:
            conn.close()
        items = []
        for r in rows:
            b = notes._row(r)
            contenido = b.get("contenido") or ""
            items.append(
                {
                    "id": b["id"],
                    "titulo": b["titulo"],
                    "contenido": contenido[:200],
                    "etiquetas": b["etiquetas"],
                }
            )
        res["notas"] = items
        total += len(items)

    if quiere("eventos"):
        conn = calendar._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM events "
                "WHERE titulo LIKE ? OR lugar LIKE ? OR notas LIKE ? "
                "ORDER BY inicio DESC LIMIT ?",
                (pat, pat, pat, lim),
            ).fetchall()
        finally:
            conn.close()
        items = []
        for r in rows:
            b = calendar._row(r)
            items.append(
                {
                    "id": b["id"],
                    "titulo": b["titulo"],
                    "inicio": b["inicio"],
                    "lugar": b["lugar"],
                    "estado": b["estado"],
                    "etiquetas": b["etiquetas"],
                }
            )
        res["eventos"] = items
        total += len(items)

    if quiere("recordatorios"):
        conn = reminders._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE texto LIKE ? ORDER BY id DESC LIMIT ?",
                (pat, lim),
            ).fetchall()
        finally:
            conn.close()
        items = []
        for r in rows:
            b = reminders._row(r)
            items.append(
                {
                    "id": b["id"],
                    "texto": b["texto"],
                    "cuando": b["cuando"],
                    "estado": b["estado"],
                    "etiquetas": b["etiquetas"],
                }
            )
        res["recordatorios"] = items
        total += len(items)

    if quiere("listas"):
        conn = lists._conn()
        try:
            rows = conn.execute(
                """SELECT DISTINCT l.* FROM lists l
                   LEFT JOIN list_items i ON i.list_id = l.id
                   WHERE l.nombre LIKE ? OR i.texto LIKE ?
                   ORDER BY l.id DESC LIMIT ?""",
                (pat, pat, lim),
            ).fetchall()
            items = []
            for r in rows:
                items.append(
                    {
                        "id": r["id"],
                        "nombre": r["nombre"],
                        "items": [
                            x["texto"]
                            for x in conn.execute(
                                "SELECT texto FROM list_items WHERE list_id = ? "
                                "ORDER BY hecho, id",
                                (r["id"],),
                            ).fetchall()
                        ],
                    }
                )
        finally:
            conn.close()
        res["listas"] = items
        total += len(items)

    res["total"] = total
    return res


def listar_etiquetas() -> dict:
    """Enumera todas las etiquetas usadas y en que dominios aparecen."""
    conteo: dict[str, dict] = {}

    def add(tag: str, dominio: str) -> None:
        c = conteo.setdefault(tag, {"etiqueta": tag, "total": 0, "dominios": {}})
        c["total"] += 1
        c["dominios"][dominio] = c["dominios"].get(dominio, 0) + 1

    fuentes = (
        ("tareas", tasks, "tasks"),
        ("notas", notes, "notes"),
        ("eventos", calendar, "events"),
        ("recordatorios", reminders, "reminders"),
    )
    for dominio, mod, tabla in fuentes:
        conn = mod._conn()
        try:
            rows = conn.execute(f"SELECT etiquetas FROM {tabla}").fetchall()
        finally:
            conn.close()
        for r in rows:
            for tag in tags_lista(r["etiquetas"]):
                add(tag, dominio)

    etiquetas = sorted(conteo.values(), key=lambda c: (-c["total"], c["etiqueta"]))
    return {"total": len(etiquetas), "etiquetas": etiquetas}
