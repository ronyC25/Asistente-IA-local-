from __future__ import annotations

import pytest

from src.brain.confirm import (
    classify_confirmation,
    looks_like_action,
    looks_like_query,
    quiere_historial_recordatorios,
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
