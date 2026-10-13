from __future__ import annotations

import pytest

from src import config
from src.tools import lists


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    config.settings.database = str(tmp_path / "test.db")
    lists._conn().close()
    yield


def test_crear_agregar_y_ver():
    lista = lists.gestionar_listas("crear", nombre="Compra")
    lists.gestionar_listas("agregar", id=lista["id"], texto="leche")
    lists.gestionar_listas("agregar", id=lista["id"], texto="pan")
    res = lists.consultar_listas("ver", id=lista["id"])
    assert res["total"] == 2
    assert {i["texto"] for i in res["items"]} == {"leche", "pan"}


def test_marcar_y_desmarcar_item():
    lista = lists.gestionar_listas("crear", nombre="Tareas")
    lists.gestionar_listas("agregar", id=lista["id"], texto="lavar")
    item = lists.consultar_listas("ver", id=lista["id"])["items"][0]
    m = lists.gestionar_listas("marcar", item_id=item["id"])
    assert m["hecho"] == 1
    d = lists.gestionar_listas("desmarcar", item_id=item["id"])
    assert d["hecho"] == 0


def test_listar_con_conteos():
    lista = lists.gestionar_listas("crear", nombre="X")
    lists.gestionar_listas("agregar", id=lista["id"], texto="a")
    res = lists.consultar_listas("listar")
    assert res["listas"][0]["total"] == 1
    assert res["listas"][0]["hechos"] == 0


def test_eliminar_lista_borra_items():
    lista = lists.gestionar_listas("crear", nombre="X")
    lists.gestionar_listas("agregar", id=lista["id"], texto="a")
    d = lists.gestionar_listas("eliminar_lista", id=lista["id"])
    assert d["eliminada"] is True
    assert lists.consultar_listas("listar")["total"] == 0


def test_agregar_sin_texto():
    lista = lists.gestionar_listas("crear", nombre="X")
    with pytest.raises(ValueError):
        lists.gestionar_listas("agregar", id=lista["id"])
