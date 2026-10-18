from __future__ import annotations

from datetime import date

import pytest

from src.brain.confirm import (
    buscar_termino_de_texto,
    classify_confirmation,
    dominio_lectura,
    es_busqueda,
    etiqueta_de_texto,
    fecha_de_texto,
    looks_like_action,
    looks_like_query,
    orden_de_texto,
    periodo_de_texto,
    pregunta_cuanto_falta,
    quiere_historial_recordatorios,
    quiere_proximo,
    rango_de_texto,
)


@pytest.mark.parametrize("text", ["sí", "si", "Claro", "confirmo", "dale", "ok", "CONFIRMAR", "sí, hazlo"])
def test_confirma(text):
    assert classify_confirmation(text) is True


@pytest.mark.parametrize("text", ["no", "No", "cancelar", "cancela", "mejor no", "negativo", "espera"])
def test_cancela(text):
    assert classify_confirmation(text) is False


@pytest.mark.parametrize("text", ["", "¿qué tareas tengo?", "quizás", "depende"])
def test_ambiguo(text):
    assert classify_confirmation(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Mándame un mensaje a Telegram con los recordatorios",
        "crea una tarea",
        "agenda una reunion",
        "envíame la lista por correo",
        "elimina la tarea 3",
        "recuérdame llamar mañana",
        "exporta el calendario",
    ],
)
def test_looks_like_action_true(text):
    assert looks_like_action(text) is True


@pytest.mark.parametrize(
    "text",
    ["¿qué tareas tengo?", "dime mis recordatorios", "cuántos eventos hay", ""],
)
def test_looks_like_action_false(text):
    assert looks_like_action(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "revisa las tareas",
        "muéstrame el calendario",
        "¿qué recordatorios tengo?",
        "lista mis eventos de hoy",
        "cuántas tareas pendientes hay",
        "lee mis correos",
    ],
)
def test_looks_like_query_true(text):
    assert looks_like_query(text) is True


@pytest.mark.parametrize("text", ["hola", "gracias", ""])
def test_looks_like_query_false(text):
    assert looks_like_query(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "hazme una lista con mis recordatorios",
        "muestrame todos mis recordatorios",
        "cuales son mis recordatorios",
    ],
)
def test_quiere_historial_true(text):
    assert quiere_historial_recordatorios(text) is True


@pytest.mark.parametrize(
    "text",
    ["que recordatorios pendientes tengo", "recordatorios de hoy", ""],
)
def test_quiere_historial_false(text):
    assert quiere_historial_recordatorios(text) is False


def test_quiere_historial_cancelados_false():
    assert quiere_historial_recordatorios("muestrame los recordatorios cancelados") is False


@pytest.mark.parametrize(
    "text,esperado",
    [
        ("cual es la agenda de los proximos 3 dias", ("proximos_dias", 3)),
        ("y en los siguientes 2 dias", ("proximos_dias", 2)),
        ("la agenda de mañana", ("manana", None)),
        ("agenda de pasado mañana", ("pasado_manana", None)),
        ("que hay el fin de semana", ("fin_de_semana", None)),
        ("algo para el finde", ("fin_de_semana", None)),
        ("tengo algo esta semana", ("esta_semana", None)),
        ("la semana que viene", ("semana_que_viene", None)),
        ("eventos de este mes", ("este_mes", None)),
        ("que hay hoy", ("hoy", None)),
        ("agenda del viernes", ("viernes", None)),
        ("muestrame mis tareas", None),
        ("crea una tarea comprar leche", None),
    ],
)
def test_periodo_de_texto(text, esperado):
    assert periodo_de_texto(text) == esperado


@pytest.mark.parametrize(
    "text,esperado",
    [
        ("una lista de las notificaciones en la base de datos", "recordatorios"),
        ("que recordatorios tengo", "recordatorios"),
        ("dime las tareas", "tareas"),
        ("muestrame las notas", "notas"),
        ("que eventos hay", "eventos"),
        ("leeme los correos", "email"),
        ("hola que tal", None),
        ("crea una tarea comprar leche", "tareas"),
    ],
)
def test_dominio_lectura(text, esperado):
    assert dominio_lectura(text) == esperado


@pytest.mark.parametrize(
    "text,esperado",
    [
        ("cual es la nota mas antigua", "antiguas"),
        ("el evento mas antiguo", "antiguas"),
        ("la nota mas reciente", "recientes"),
        ("dame las tareas", None),
    ],
)
def test_orden_de_texto(text, esperado):
    assert orden_de_texto(text) == esperado


def test_quiere_proximo():
    assert quiere_proximo("cual es el evento mas proximo") is True
    assert quiere_proximo("dame las tareas") is False


def test_pregunta_cuanto_falta():
    assert pregunta_cuanto_falta("cuanto falta para el proximo evento") is True
    assert pregunta_cuanto_falta("dame las tareas") is False


@pytest.mark.parametrize(
    "text,esperado",
    [
        ("el 28 de octubre", date(2026, 10, 28)),
        ("28 de octubre de 2027", date(2027, 10, 28)),
        ("28/10/2026", date(2026, 10, 28)),
        ("2026-10-28", date(2026, 10, 28)),
        ("dame las tareas", None),
    ],
)
def test_fecha_de_texto(text, esperado):
    assert fecha_de_texto(text, hoy=date(2026, 10, 16)) == esperado


def test_fecha_de_texto_rollover():
    # 5 de enero ya paso (hoy 16 oct 2026) -> 2027
    assert fecha_de_texto("5 de enero", hoy=date(2026, 10, 16)) == date(2027, 1, 5)


def test_rango_de_texto():
    hoy = date(2026, 10, 16)
    assert rango_de_texto("de aqui a dos semanas", hoy=hoy) == (
        date(2026, 10, 16),
        date(2026, 10, 30),
    )
    assert rango_de_texto("en 3 dias", hoy=hoy) == (
        date(2026, 10, 19),
        date(2026, 10, 19),
    )
    assert rango_de_texto("proximas 2 semanas", hoy=hoy) == (
        date(2026, 10, 16),
        date(2026, 10, 30),
    )
    assert rango_de_texto("dame las tareas", hoy=hoy) is None


def test_rango_semana_de_mes():
    hoy = date(2026, 10, 16)
    assert rango_de_texto("la ultima semana de octubre", hoy=hoy) == (
        date(2026, 10, 25),
        date(2026, 10, 31),
    )
    assert rango_de_texto("la primera semana de octubre", hoy=hoy) == (
        date(2026, 10, 1),
        date(2026, 10, 7),
    )
    assert rango_de_texto("la segunda semana de noviembre de 2027", hoy=hoy) == (
        date(2027, 11, 8),
        date(2027, 11, 14),
    )
    assert rango_de_texto("la ultima semana del mes", hoy=hoy) == (
        date(2026, 10, 25),
        date(2026, 10, 31),
    )


@pytest.mark.parametrize(
    "text",
    ["busca las llaves", "donde esta el informe", "encuentra a Juan", "buscame las pilas"],
)
def test_es_busqueda(text):
    assert es_busqueda(text)


def test_dominio_busqueda():
    assert dominio_lectura("busca las llaves") == "busqueda"
    # si hay un dominio explicito, gana el dominio (no 'busqueda')
    assert dominio_lectura("busca la tarea de compras") == "tareas"


def test_buscar_termino_de_texto():
    assert buscar_termino_de_texto("busca las llaves del coche") == "llaves coche"
    assert buscar_termino_de_texto("donde esta el informe") == "informe"
    assert buscar_termino_de_texto("busca") is None


def test_etiqueta_de_texto():
    assert etiqueta_de_texto("tareas etiquetadas como compras") == "compras"
    assert etiqueta_de_texto("dame las notas con etiqueta ideas") == "ideas"
    assert etiqueta_de_texto("que tareas tengo") is None
