"""Utilidades de fecha/hora compartidas."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from dateutil import parser as dateparser

_DIAS_SEMANA = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}

# Etiquetas aceptadas por el parametro ``periodo`` de las herramientas de listado.
PERIODOS = (
    "hoy",
    "manana",
    "pasado_manana",
    "fin_de_semana",
    "esta_semana",
    "semana_que_viene",
    "semana_pasada",
    "proximos_dias",
    "este_mes",
    *_DIAS_SEMANA,
)


def _semana_inicio(hoy: date, week_start: str | None) -> date:
    """Primer dia de la semana de ``hoy`` segun ``week_start`` (domingo|lunes)."""
    ws = 6 if str(week_start or "lunes").strip().lower() in ("domingo", "sunday", "dom") else 0
    return hoy - timedelta(days=(hoy.weekday() - ws) % 7)


def _week_start_config() -> str:
    try:
        from .config import settings

        return settings.week_start
    except Exception:  # noqa: BLE001
        return "lunes"


def _inicio_dia(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time())


def _fin_dia(d: date) -> datetime:
    return datetime.combine(d, datetime.max.time()).replace(microsecond=0)


def anio_natural(mes: int, dia: int, hoy: date | None = None) -> int:
    """Ano que corresponde a un dia/mes sin ano explicito.

    Si la fecha ya paso este ano, se usa el siguiente (igual que
    ``confirm.fecha_de_texto``). Sirve para corregir anos inventados por el
    modelo al crear eventos/tareas/recordatorios.
    """
    hoy = hoy or date.today()
    try:
        f = date(hoy.year, mes, dia)
    except ValueError:
        return hoy.year
    return f.year if f >= hoy else f.year + 1


def resolver_periodo(
    periodo: str,
    dias: int | None = None,
    ahora: datetime | None = None,
    week_start: str | None = None,
) -> tuple[datetime, datetime]:
    """Traduce una etiqueta de periodo a un rango (desde, hasta) inclusive.

    El calculo es determinista (no depende del modelo). ``proximos_dias`` usa
    ``dias`` y cuenta N dias naturales desde hoy (hoy incluido).
    """
    ahora = ahora or datetime.now()
    hoy = ahora.date()
    ws = week_start or _week_start_config()
    p = (periodo or "").strip().lower()

    if p == "hoy":
        return _inicio_dia(hoy), _fin_dia(hoy)
    if p == "manana":
        d = hoy + timedelta(days=1)
        return _inicio_dia(d), _fin_dia(d)
    if p == "pasado_manana":
        d = hoy + timedelta(days=2)
        return _inicio_dia(d), _fin_dia(d)
    if p == "fin_de_semana":
        wd = hoy.weekday()
        sab = hoy + timedelta(days=5 - wd) if wd <= 4 else hoy - timedelta(days=wd - 5)
        return _inicio_dia(sab), _fin_dia(sab + timedelta(days=1))
    if p == "esta_semana":
        ini = _semana_inicio(hoy, ws)
        return _inicio_dia(ini), _fin_dia(ini + timedelta(days=6))
    if p == "semana_que_viene":
        ini = _semana_inicio(hoy, ws) + timedelta(days=7)
        return _inicio_dia(ini), _fin_dia(ini + timedelta(days=6))
    if p == "semana_pasada":
        ini = _semana_inicio(hoy, ws) - timedelta(days=7)
        return _inicio_dia(ini), _fin_dia(ini + timedelta(days=6))
    if p == "este_mes":
        ini = hoy.replace(day=1)
        fin = (
            ini.replace(year=ini.year + 1, month=1, day=1)
            if ini.month == 12
            else ini.replace(month=ini.month + 1, day=1)
        ) - timedelta(days=1)
        return _inicio_dia(ini), _fin_dia(fin)
    if p == "proximos_dias":
        n = max(1, int(dias) if dias else 3)
        return _inicio_dia(hoy), _fin_dia(hoy + timedelta(days=n - 1))
    if p in _DIAS_SEMANA:
        d = hoy + timedelta(days=(_DIAS_SEMANA[p] - hoy.weekday()) % 7)
        return _inicio_dia(d), _fin_dia(d)
    raise ValueError(f"periodo no valido: {periodo!r}")


def faltan_texto(objetivo: datetime, ahora: datetime | None = None) -> str:
    """Texto humano de cuanto falta (o ha pasado) hasta ``objetivo``.

    Se calcula en codigo para que el modelo no tenga que hacer la aritmetica.
    """
    ahora = ahora or datetime.now()
    seg = (objetivo - ahora).total_seconds()
    futuro = seg >= 0
    seg = abs(seg)
    dias = int(seg // 86400)
    horas = int((seg % 86400) // 3600)
    minutos = int((seg % 3600) // 60)
    if dias > 0:
        base = f"{dias} d" + (f" {horas} h" if horas else "")
    elif horas > 0:
        base = f"{horas} h" + (f" {minutos} min" if minutos else "")
    else:
        base = f"{minutos} min"
    return f"en {base}" if futuro else f"hace {base}"


def _sin_hora(value: str) -> bool:
    return ":" not in str(value)


def parse_datetime(value: str, future: bool = False, end_of_day: bool = False) -> datetime:
    """Parsea una fecha/hora ISO. Si future=True exige que sea en el futuro.

    Si ``end_of_day=True`` y el valor no trae hora (p. ej. '2026-10-28'), se usa
    el final de ese dia (23:59:59) para no excluir los eventos del propio dia.
    """
    try:
        dt = dateparser.parse(str(value), fuzzy=False)
    except (ValueError, OverflowError, TypeError):
        dt = None
    if dt is None:
        raise ValueError(
            f"fecha/hora no valida: {value!r}. Usa formato ISO "
            "(YYYY-MM-DD o YYYY-MM-DD HH:MM)."
        )
    if end_of_day and _sin_hora(value):
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=0)
    if future and dt < datetime.now():
        raise ValueError(
            f"la fecha/hora {dt.isoformat(timespec='minutes')} ya paso."
        )
    return dt
