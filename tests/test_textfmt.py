from __future__ import annotations

from src.brain.emotions import limpiar_respuesta
from src.brain.textfmt import strip_markdown


def test_quita_negritas():
    assert strip_markdown("**Recordatorio** importante") == "Recordatorio importante"


def test_quita_cursiva_y_code():
    assert strip_markdown("Esto es *italica* y `codigo`.") == "Esto es italica y codigo."


def test_quita_titulos_y_bullets():
    out = strip_markdown("# Titulo\n- uno\n- dos")
    assert "#" not in out and "*" not in out
    assert "• uno" in out


def test_quita_asteriscos_sueltos():
    out = strip_markdown("2 * 3 = 6 **x**")
    assert "*" not in out


def test_limpiar_respuesta_emocion_y_markdown():
    limpio, emociones = limpiar_respuesta("[joy] **Hola** amigo")
    assert emociones == ["joy"]
    assert limpio == "Hola amigo"
