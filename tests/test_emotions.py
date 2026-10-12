from __future__ import annotations

from src.brain.emotions import strip_emotions


def test_extrae_emocion_inicial():
    limpio, emociones = strip_emotions("[joy] Hola, que alegria verte.")
    assert limpio == "Hola, que alegria verte."
    assert emociones == ["joy"]


def test_emocion_intermedia():
    limpio, emociones = strip_emotions("Vale [neutral] hecho.")
    assert limpio == "Vale hecho."
    assert emociones == ["neutral"]


def test_varias_emociones():
    limpio, emociones = strip_emotions("[sad] Lo siento [relaxed] tranquilo")
    assert emociones == ["sad", "relaxed"]
    assert "[" not in limpio


def test_etiqueta_desconocida_se_conserva():
    limpio, emociones = strip_emotions("Usa [CODIGO] aqui")
    assert limpio == "Usa [CODIGO] aqui"
    assert emociones == []


def test_texto_vacio():
    limpio, emociones = strip_emotions("")
    assert limpio == ""
    assert emociones == []
