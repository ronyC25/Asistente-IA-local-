"""Utilidades de etiquetas: normalizacion, parseo y filtrado SQL.

Las etiquetas se guardan como texto separado por comas y normalizado
(minusculas, sin acentos, con guiones). Ej: ``"trabajo,urgente"``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


def _norm_one(t: Any) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = t.encode("ascii", "ignore").decode("ascii")
    t = t.lower().strip()
    t = re.sub(r"[\s_]+", "-", t)
    t = re.sub(r"[^a-z0-9\-]", "", t)
    return t.strip("-")


def normalizar(etiquetas: Any) -> str | None:
    """Normaliza etiquetas (lista, tupla o string con comas) -> 'a,b,c' o None."""
    if etiquetas is None:
        return None
    if isinstance(etiquetas, str):
        items: Iterable[Any] = re.split(r"[,\n;]+", etiquetas)
    else:
        try:
            items = list(etiquetas)
        except TypeError:
            items = [etiquetas]
    out: list[str] = []
    for it in items:
        n = _norm_one(it)
        if n and n not in out:
            out.append(n)
    return ",".join(out) if out else None


def lista(etiquetas: str | None) -> list[str]:
    """Convierte la columna 'a,b,c' en lista ``['a', 'b', 'c']``."""
    if not etiquetas:
        return []
    return [e for e in str(etiquetas).split(",") if e]


def filtro_sql(columna: str = "etiquetas") -> str:
    """Fragmento SQL (con 4 placeholders) que casa una etiqueta exacta en la lista."""
    return f"({columna} = ? OR {columna} LIKE ? OR {columna} LIKE ? OR {columna} LIKE ?)"


def filtro_params(etiqueta: str) -> list[str]:
    """Parametros para ``filtro_sql`` (etiqueta exacta, al inicio, al final, en medio)."""
    n = _norm_one(etiqueta)
    return [n, f"{n},%", f"%,{n}", f"%,{n},%"]
