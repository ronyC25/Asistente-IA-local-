from __future__ import annotations

from src.brain.voice_guard import parece_eco

REPLY = (
    "Los eventos de esta semana son: Examen de Unidad Seguridad de la "
    "informacion y Examen Parcial topicos."
)


def test_eco_de_frase_del_asistente():
    assert parece_eco("Examen de Unidad Seguridad de la informacion", REPLY)
    assert parece_eco("Examen Parcial topicos", REPLY)


def test_pregunta_no_es_eco():
    assert not parece_eco("Cuando es el examen de unidad seguridad", REPLY)


def test_accion_no_es_eco():
    assert not parece_eco("cancela el examen de unidad seguridad", REPLY)


def test_frase_corta_no_es_eco():
    assert not parece_eco("hola", REPLY)
    assert not parece_eco("si", REPLY)


def test_texto_distinto_no_es_eco():
    assert not parece_eco("quiero crear una tarea para el sabado", REPLY)


def test_sin_referencia():
    assert not parece_eco("cualquier cosa", None)
    assert not parece_eco("", REPLY)
