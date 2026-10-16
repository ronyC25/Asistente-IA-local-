from __future__ import annotations

import pytest

from src import config
from src.tools import notes


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    config.settings.database = str(tmp_path / "test.db")
    notes._conn().close()
    yield


def test_crear_y_listar():
    n = notes.gestionar_notas("crear", titulo="Idea", contenido="Comprar dominio")
    assert n["titulo"] == "Idea"
    res = notes.consultar_notas("listar")
    assert res["total"] == 1
    assert res["notas"][0]["contenido"] == "Comprar dominio"


def test_buscar():
    notes.gestionar_notas("crear", contenido="receta de pizza")
    notes.gestionar_notas("crear", contenido="lista de la compra")
    res = notes.consultar_notas("buscar", texto="pizza")
    assert res["total"] == 1
    assert "pizza" in res["notas"][0]["contenido"]


def test_editar_y_eliminar():
    n = notes.gestionar_notas("crear", titulo="T", contenido="v1")
    e = notes.gestionar_notas("editar", id=n["id"], contenido="v2")
    assert e["contenido"] == "v2"
    d = notes.gestionar_notas("eliminar", id=n["id"])
    assert d["eliminada"] is True
    assert notes.consultar_notas("listar")["total"] == 0


def test_crear_sin_contenido():
    with pytest.raises(ValueError):
        notes.gestionar_notas("crear", titulo="solo titulo")


def test_eliminar_inexistente():
    with pytest.raises(ValueError):
        notes.gestionar_notas("eliminar", id=999)


def test_listar_orden_antiguas():
    notes.gestionar_notas("crear", contenido="primera")
    notes.gestionar_notas("crear", contenido="segunda")
    res = notes.consultar_notas("listar", orden="antiguas", limite=1)
    assert res["total"] == 1
    assert res["notas"][0]["contenido"] == "primera"


def test_listar_por_periodo():
    notes.gestionar_notas("crear", contenido="hoy")
    assert notes.consultar_notas("listar", periodo="hoy")["total"] == 1
    assert notes.consultar_notas("listar", periodo="manana")["total"] == 0
