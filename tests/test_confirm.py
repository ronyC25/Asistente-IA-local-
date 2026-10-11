from __future__ import annotations

import pytest

from src.brain.confirm import classify_confirmation, looks_like_action


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
