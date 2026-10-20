from __future__ import annotations

from src.brain.tooltext import extraer_llamadas, parece_llamada

NOMBRES = {"listar_eventos", "crear_tarea"}


def test_json_simple():
    t = '{"name": "listar_eventos", "arguments": {"periodo": "esta_semana"}}'
    assert extraer_llamadas(t, NOMBRES) == [
        ("listar_eventos", {"periodo": "esta_semana"})
    ]
    assert parece_llamada(t, NOMBRES)


def test_json_con_texto_y_fence():
    t = 'Claro:\n```json\n{"name":"crear_tarea","arguments":{"titulo":"X"}}\n```'
    assert extraer_llamadas(t, NOMBRES) == [("crear_tarea", {"titulo": "X"})]


def test_arguments_como_string():
    t = '{"name": "listar_eventos", "arguments": "{\\"periodo\\": \\"hoy\\"}"}'
    assert extraer_llamadas(t, NOMBRES) == [("listar_eventos", {"periodo": "hoy"})]


def test_tag_tool_call():
    t = '<tool_call>{"name": "listar_eventos", "arguments": {"limite": 1}}</tool_call>'
    assert extraer_llamadas(t, NOMBRES) == [("listar_eventos", {"limite": 1})]
    assert parece_llamada(t, NOMBRES)


def test_funcion_parentesis():
    t = 'listar_eventos({"periodo": "hoy"})'
    assert extraer_llamadas(t, NOMBRES) == [("listar_eventos", {"periodo": "hoy"})]


def test_nombre_invalido():
    t = '{"name": "inventada", "arguments": {}}'
    assert extraer_llamadas(t, NOMBRES) == []
    assert parece_llamada(t, NOMBRES) is False
    # Sin lista de nombres validos, cualquier JSON con "name" es sospechoso.
    assert parece_llamada(t) is True


def test_texto_normal():
    assert extraer_llamadas("Hola, ¿qué tal?", NOMBRES) == []
    assert parece_llamada("Tienes 2 tareas.", NOMBRES) is False


def test_json_anidado_y_varios():
    t = (
        "primero "
        '{"name": "listar_eventos", "arguments": {"limite": 1, "x": {"a": 2}}} '
        "y luego "
        '{"name": "crear_tarea", "arguments": {"titulo": "Otra"}}'
    )
    assert extraer_llamadas(t, NOMBRES) == [
        ("listar_eventos", {"limite": 1, "x": {"a": 2}}),
        ("crear_tarea", {"titulo": "Otra"}),
    ]
