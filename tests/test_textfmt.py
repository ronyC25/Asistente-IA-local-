from __future__ import annotations

from src.brain.emotions import limpiar_respuesta
from src.brain.textfmt import strip_markdown, strip_think


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


def test_strip_think():
    assert strip_think("<think>razonando</think>Hola") == "Hola"
    assert strip_think("<think>razonando sin cerrar") == ""
    assert strip_think("Hola") == "Hola"


def test_limpiar_respuesta_quita_think():
    limpio, _ = limpiar_respuesta("[neutral]<think>mucho razonamiento</think> Tienes 2 tareas.")
    assert limpio == "Tienes 2 tareas."
    assert "think" not in limpio
