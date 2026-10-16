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
    agent._execute = lambda name, args: {"ok": True, "resultado": {"total": 0}}
    s = agent.new_session()
    reply, info = agent.handle(s, "revisa las tareas")
    assert info is None
    assert reply == "Estoy revisando..."
    # 1er intento y nudge sin thinking; 2º reintento con thinking; luego el
    # fallback determinista ejecuta la lectura (otra llamada, sin thinking).
    assert agent.client.thinks == [False, False, True, False]


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


def test_ajustar_args_periodo_proximos_dias():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {"desde": "2026-10-17", "hasta": "2026-10-19"})]
    out = agent._ajustar_args(parsed, "agenda de los proximos 3 dias")
    assert out == [("listar_eventos", {"periodo": "proximos_dias", "dias": 3})]


def test_ajustar_args_periodo_manana():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {"desde": "2026-10-17", "hasta": "2026-10-18"})]
    out = agent._ajustar_args(parsed, "cual es la agenda de mañana")
    assert out == [("listar_eventos", {"periodo": "manana"})]


def test_ajustar_args_sin_fechas_no_toca():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {"desde": "2026-10-20"})]
    out = agent._ajustar_args(parsed, "que eventos tengo")
    assert out == [("listar_eventos", {"desde": "2026-10-20"})]


def test_ajustar_args_periodo_en_tareas():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_tareas", {"estado": "pendientes"})]
    out = agent._ajustar_args(parsed, "que tareas tengo esta semana")
    assert out == [
        ("listar_tareas", {"estado": "pendientes", "periodo": "esta_semana"})
    ]


def test_ajustar_args_inyecta_lectura_del_dominio():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    # El modelo se equivoca: llama a notas cuando piden "notificaciones".
    parsed = [("consultar_notas", {"accion": "listar"})]
    out = agent._ajustar_args(
        parsed, "una lista de las notificaciones en la base de datos"
    )
    names = [n for n, _ in out]
    assert "listar_recordatorios" in names
    assert dict(out)["listar_recordatorios"].get("estado") == "historial"


def test_ajustar_args_no_inyecta_en_acciones():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("crear_tarea", {"titulo": "comprar leche"})]
    out = agent._ajustar_args(parsed, "crea una tarea: comprar leche")
    assert [n for n, _ in out] == ["crear_tarea"]


def test_fallback_lectura_si_el_modelo_no_llama_tool():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _FakeClient()  # siempre responde texto, sin tool_calls
    llamadas: list[str] = []

    def fake_exec(name, args):
        llamadas.append(name)
        return {"ok": True, "resultado": {"total": 0}}

    agent._execute = fake_exec
    s = agent.new_session()
    reply, info = agent.handle(
        s, "una lista de las notificaciones en la base de datos"
    )
    assert info is None
    assert "listar_recordatorios" in llamadas


def test_cortador_de_bucle():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    tool_call = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "listar_tareas", "arguments": {}}}],
        }
    }
    final = {"message": {"role": "assistant", "content": "Tienes 0 tareas."}}
    agent.client = _ScriptClient([tool_call, tool_call, final])
    agent._execute = lambda name, args: {"ok": True, "resultado": {"total": 0}}
    s = agent.new_session()
    reply, info = agent.handle(s, "que tareas tengo")
    assert reply == "Tienes 0 tareas."
    assert info is None


def test_ajustar_args_nota_antigua():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("consultar_notas", {"accion": "listar"})]
    out = agent._ajustar_args(parsed, "cual es la nota mas antigua")
    d = dict(out)["consultar_notas"]
    assert d["orden"] == "antiguas"
    assert d["limite"] == 1


def test_ajustar_args_evento_proximo():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {})]
    out = agent._ajustar_args(parsed, "cual es el evento mas proximo")
    assert dict(out)["listar_eventos"].get("limite") == 1


def test_ajustar_args_evento_antiguo():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {})]
    out = agent._ajustar_args(parsed, "cual es el evento mas antiguo")
    d = dict(out)["listar_eventos"]
    assert d["orden"] == "antiguos"
    assert d["limite"] == 1


def test_ajustar_args_notas_periodo():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("consultar_notas", {"accion": "listar"})]
    out = agent._ajustar_args(parsed, "dame las notas de esta semana")
    assert dict(out)["consultar_notas"].get("periodo") == "esta_semana"


def test_ajustar_args_fecha_explicita():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {})]
    out = agent._ajustar_args(parsed, "que eventos hay el 28 de octubre")
    d = dict(out)["listar_eventos"]
    assert d.get("desde") and d.get("hasta")
    assert d["desde"] == d["hasta"]


def test_ajustar_args_rango_semanas():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {})]
    out = agent._ajustar_args(parsed, "eventos de aqui a dos semanas")
    d = dict(out)["listar_eventos"]
    assert d.get("desde") and d.get("hasta")
    assert d["desde"] != d["hasta"]
