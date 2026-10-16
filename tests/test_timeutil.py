from __future__ import annotations

from datetime import datetime

import pytest

from src.timeutil import faltan_texto, resolver_periodo


def _jueves() -> datetime:
    # 2026-10-15 es jueves
    return datetime(2026, 10, 15, 23, 0)


def test_hoy():
    d, h = resolver_periodo("hoy", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-15"
    assert h.date().isoformat() == "2026-10-15"


def test_manana():
    d, _ = resolver_periodo("manana", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-16"


def test_pasado_manana():
    d, _ = resolver_periodo("pasado_manana", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-17"


def test_proximos_dias():
    d, h = resolver_periodo("proximos_dias", dias=3, ahora=_jueves())
    assert d.date().isoformat() == "2026-10-15"
    assert h.date().isoformat() == "2026-10-17"


def test_proximos_dias_por_defecto():
    d, h = resolver_periodo("proximos_dias", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-15"
    assert h.date().isoformat() == "2026-10-17"


def test_fin_de_semana_desde_jueves():
    d, h = resolver_periodo("fin_de_semana", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-17"
    assert h.date().isoformat() == "2026-10-18"


def test_fin_de_semana_en_domingo():
    domingo = datetime(2026, 10, 18, 10, 0)
    d, h = resolver_periodo("fin_de_semana", ahora=domingo)
    assert d.date().isoformat() == "2026-10-17"
    assert h.date().isoformat() == "2026-10-18"


def test_esta_semana():
    d, h = resolver_periodo("esta_semana", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-12"  # lunes
    assert h.date().isoformat() == "2026-10-18"  # domingo


def test_semana_que_viene():
    d, h = resolver_periodo("semana_que_viene", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-19"
    assert h.date().isoformat() == "2026-10-25"


def test_este_mes():
    d, h = resolver_periodo("este_mes", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-01"
    assert h.date().isoformat() == "2026-10-31"


def test_dia_semana_proximo():
    d, _ = resolver_periodo("viernes", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-16"


def test_dia_semana_es_hoy():
    d, _ = resolver_periodo("jueves", ahora=_jueves())
    assert d.date().isoformat() == "2026-10-15"


def test_periodo_invalido():
    with pytest.raises(ValueError):
        resolver_periodo("banana", ahora=_jueves())


def test_faltan_texto():
    base = datetime(2026, 10, 15, 11, 0)
    assert faltan_texto(datetime(2026, 10, 15, 12, 0), base) == "en 1 h"
    assert faltan_texto(datetime(2026, 10, 15, 10, 0), base) == "hace 1 h"
    assert faltan_texto(datetime(2026, 10, 18, 11, 0), base) == "en 3 d"
    assert faltan_texto(datetime(2026, 10, 15, 11, 30), base) == "en 30 min"
