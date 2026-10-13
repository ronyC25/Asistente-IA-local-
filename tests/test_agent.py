from __future__ import annotations

from src.brain.agent import Agent, partition_calls
from src.brain.registry import Registry
from src.brain.schema import build_tools


def _registry() -> Registry:
    r = Registry()
    for spec in build_tools():
        r.add(spec)
    return r


def test_partition_calls():
    r = _registry()
    parsed = [
        ("listar_recordatorios", {}),
        ("enviar_telegram", {"mensaje": "x"}),
    ]
    reads, writes = partition_calls(parsed, r)
    assert reads == [("listar_recordatorios", {})]
    assert writes == [("enviar_telegram", {"mensaje": "x"})]


def test_pending_ambiguo_repite_y_conserva():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    s = agent.new_session()
    s.pending = [("crear_tarea", {"titulo": "Comprar leche"})]
    reply, info = agent.handle(s, "¿qué hora es?")
    assert info == {"type": "confirm"}
    assert s.pending is not None
    assert "Comprar leche" in reply


def test_pending_se_cancela():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    s = agent.new_session()
    s.pending = [("crear_tarea", {"titulo": "Comprar leche"})]
    # "no" cancela; no debe intentar llamar al modelo con el cliente real
    agent.client = _FakeClient()
    reply, info = agent.handle(s, "no")
    assert s.pending is None
    assert info is None


class _FakeClient:
    def chat(self, **kwargs):
        return {"message": {"role": "assistant", "content": "accion cancelada"}}


class _ScriptClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, **kwargs):
        return self._responses.pop(0)


def test_nudge_fuerza_escritura():
    # 1) el modelo solo narra; 2) tras el nudge llama a enviar_telegram
    responses = [
        {"message": {"role": "assistant", "content": "Envio ahora un mensaje a Telegram..."}},
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "enviar_telegram", "arguments": {"mensaje": "lista"}}}
                ],
            }
        },
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    s = agent.new_session()
    reply, info = agent.handle(s, "Mándame un mensaje a Telegram con los recordatorios")
    assert info == {"type": "confirm"}
    assert "Enviar por Telegram" in reply


def test_nudge_recupera_rechazo():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": "No tengo la capacidad de enviar mensajes directamente a Telegram.",
            }
        },
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "enviar_telegram", "arguments": {"mensaje": "x"}}}
                ],
            }
        },
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    s = agent.new_session()
    reply, info = agent.handle(s, "Mándame un mensaje a Telegram")
    assert info == {"type": "confirm"}
    assert "Enviar por Telegram" in reply


def test_sin_nudge_en_saludo():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(
        [{"message": {"role": "assistant", "content": "Hola, ¿en qué ayudo?"}}]
    )
    s = agent.new_session()
    reply, info = agent.handle(s, "hola")
    assert info is None
    assert reply == "Hola, ¿en qué ayudo?"


class _CaptureClient:
    def __init__(self):
        self.kwargs = None

    def chat(self, **kwargs):
        self.kwargs = kwargs
        return {"message": {"role": "assistant", "content": "ok"}}


def test_call_pasa_opciones():
    agent = Agent(
        _registry(),
        model="dummy",
        system_prompt="sys",
        num_predict=400,
        keep_alive="30m",
    )
    agent.client = _CaptureClient()
    agent.handle(agent.new_session(), "hola")
    kw = agent.client.kwargs
    assert kw["think"] is False
    assert kw["options"]["num_predict"] == 400
    assert kw["options"]["num_ctx"] == 4096
    assert kw["keep_alive"] == "30m"


def test_keep_alive_omitido_si_none():
    agent = Agent(
        _registry(), model="dummy", system_prompt="sys", keep_alive=None
    )
    agent.client = _CaptureClient()
    agent.handle(agent.new_session(), "hola")
    assert "keep_alive" not in agent.client.kwargs


def test_trim_historial():
    agent = Agent(
        _registry(), model="dummy", system_prompt="sys", history_limit=4
    )
    s = agent.new_session()
    for i in range(20):
        s.messages.append({"role": "user", "content": f"u{i}"})
        s.messages.append({"role": "assistant", "content": f"a{i}"})
    agent._trim(s)
    assert s.messages[0]["role"] == "system"
    assert len(s.messages) <= 5
    assert s.messages[1]["role"] == "user"


def test_trim_quita_tool_huerfano():
    agent = Agent(
        _registry(), model="dummy", system_prompt="sys", history_limit=2
    )
    s = agent.new_session()
    s.messages += [
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "", "tool_calls": [{"x": 1}]},
        {"role": "tool", "content": "{}"},
        {"role": "assistant", "content": "a1"},
    ]
    agent._trim(s)
    assert s.messages[0]["role"] == "system"
    assert s.messages[1]["role"] != "tool"


def test_nudge_lectura_recupera():
    responses = [
        {"message": {"role": "assistant", "content": "Estoy revisando, un momento..."}},
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "fecha_hora_actual", "arguments": {}}}
                ],
            }
        },
        {"message": {"role": "assistant", "content": "Hoy es lunes."}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    s = agent.new_session()
    reply, info = agent.handle(s, "revisa las tareas y dime la fecha")
    assert info is None
    assert reply == "Hoy es lunes."


class _NarratingClient:
    def __init__(self):
        self.thinks: list = []

    def chat(self, **kwargs):
        self.thinks.append(kwargs.get("think"))
        return {"message": {"role": "assistant", "content": "Estoy revisando..."}}


def test_reintento_con_thinking():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NarratingClient()
    s = agent.new_session()
    reply, info = agent.handle(s, "revisa las tareas")
    assert info is None
    assert reply == "Estoy revisando..."
    # 1er intento y nudge sin thinking; 2º reintento con thinking.
    assert agent.client.thinks == [False, False, True]


def test_ajustar_args_historial():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_recordatorios", {"estado": "pendientes"})]
    out = agent._ajustar_args(parsed, "hazme una lista con mis recordatorios")
    assert out == [("listar_recordatorios", {"estado": "historial"})]


def test_ajustar_args_todos_a_historial():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_recordatorios", {"estado": "todos"})]
    out = agent._ajustar_args(parsed, "muestrame todos mis recordatorios")
    assert out == [("listar_recordatorios", {"estado": "historial"})]


def test_ajustar_args_respeta_cancelados():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_recordatorios", {"estado": "cancelados"})]
    out = agent._ajustar_args(parsed, "muestrame los recordatorios cancelados")
    assert out == [("listar_recordatorios", {"estado": "cancelados"})]


def test_ajustar_args_respeta_pendientes():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_recordatorios", {})]
    out = agent._ajustar_args(parsed, "que recordatorios pendientes tengo?")
    assert out == [("listar_recordatorios", {})]
