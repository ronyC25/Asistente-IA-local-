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


def test_sin_nudge_en_consulta():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(
        [{"message": {"role": "assistant", "content": "Tienes 3 tareas."}}]
    )
    s = agent.new_session()
    reply, info = agent.handle(s, "¿Qué tareas tengo?")
    assert info is None
    assert reply == "Tienes 3 tareas."
