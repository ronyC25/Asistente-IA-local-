"""Utilidades de fecha/hora compartidas."""
from __future__ import annotations

from datetime import datetime

from dateutil import parser as dateparser


def parse_datetime(value: str, future: bool = False) -> datetime:
    """Parsea una fecha/hora ISO. Si future=True exige que sea en el futuro."""
    try:
        dt = dateparser.parse(str(value), fuzzy=False)
    except (ValueError, OverflowError, TypeError):
        dt = None
    if dt is None:
        raise ValueError(
            f"fecha/hora no valida: {value!r}. Usa formato ISO "
            "(YYYY-MM-DD o YYYY-MM-DD HH:MM)."
        )
    if future and dt < datetime.now():
        raise ValueError(
            f"la fecha/hora {dt.isoformat(timespec='minutes')} ya paso."
        )
    return dt
