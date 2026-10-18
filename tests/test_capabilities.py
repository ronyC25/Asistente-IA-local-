from __future__ import annotations

from src.brain.capabilities import texto_capacidades
from src.brain.registry import Registry
from src.brain.schema import build_tools


def _registry() -> Registry:
    r = Registry()
    for spec in build_tools():
        r.add(spec)
    return r


def test_texto_incluye_grupos():
    txt = texto_capacidades(_registry(), nombre="Jarvis")
    assert "Soy Jarvis" in txt
    for grupo in (
        "Tareas",
        "Recordatorios",
        "Notas",
        "Listas",
        "Busqueda",
        "Calendario",
        "Mensajeria",
        "Sistema",
    ):
        assert grupo in txt
    assert "Prueba a decir" in txt


def test_solo_grupos_con_tools_existentes():
    txt = texto_capacidades(Registry(), nombre="X")
    assert "Tareas" not in txt
    assert "Prueba a decir" in txt


def test_texto_completo_no_truncado():
    txt = texto_capacidades(_registry())
    # una linea por grupo disponible (8) + ejemplos
    assert txt.count("- ") >= 8
