from __future__ import annotations

from src.brain.agent import Agent, partition_calls
from src.brain.registry import Registry
from src.brain.schema import build_tools
from src.timeutil import anio_natural


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


def test_ajustar_args_ultima_semana_de_mes():
    from datetime import date

    y = date.today().year
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {})]
    out = agent._ajustar_args(parsed, "eventos de la ultima semana de octubre")
    d = dict(out)["listar_eventos"]
    assert d["desde"] == f"{y}-10-25"
    assert d["hasta"] == f"{y}-10-31"


def test_ajustar_args_inyecta_busqueda():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    out = agent._ajustar_args([], "busca las llaves del coche")
    d = dict(out)
    assert "buscar_todo" in d
    assert d["buscar_todo"]["texto"] == "llaves coche"


def test_ajustar_args_etiqueta_en_listado():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_tareas", {})]
    out = agent._ajustar_args(parsed, "tareas etiquetadas como compras")
    assert dict(out)["listar_tareas"]["etiqueta"] == "compras"


def test_ajustar_args_no_inyecta_busqueda_en_accion():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("crear_tarea", {"titulo": "x"})]
    out = agent._ajustar_args(parsed, "crea una tarea y busca las llaves")
    assert [n for n, _ in out] == ["crear_tarea"]


def test_ajustar_args_cuanto_falta_quita_periodo_inventado():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {"periodo": "proximos_dias"})]
    out = agent._ajustar_args(parsed, "cuanto falta para el proximo evento")
    d = dict(out)["listar_eventos"]
    assert "periodo" not in d
    assert d["limite"] == 1


def test_ajustar_args_cuanto_falta_respeta_periodo_explicito():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("listar_eventos", {})]
    out = agent._ajustar_args(parsed, "cuanto falta para el evento de esta semana")
    assert dict(out)["listar_eventos"].get("periodo") == "esta_semana"


class _NoCallClient:
    def __init__(self) -> None:
        self.called = False

    def chat(self, **kwargs):
        self.called = True
        return {"message": {"role": "assistant", "content": "no deberia llamarse"}}


def test_handle_capacidades_sin_llamar_modelo():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NoCallClient()
    s = agent.new_session()
    reply, info = agent.handle(s, "¿Qué puedes hacer?")
    assert info is None
    assert agent.client.called is False
    assert "Tareas" in reply
    assert "Recordatorios" in reply


def test_handle_ayuda_slash():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NoCallClient()
    reply, info = agent.handle(agent.new_session(), "/ayuda")
    assert info is None
    assert "Calendario" in reply


def test_handle_inicia_temporizador(monkeypatch):
    from src.tools import timers

    llamadas: list[dict] = []

    def _fake_iniciar(**k):
        llamadas.append(k)
        return {
            "tipo": k.get("tipo", "temporizador"),
            "etiqueta": k.get("etiqueta"),
            "duracion_min": k.get("minutos") or 25,
        }

    monkeypatch.setattr(timers, "iniciar", _fake_iniciar)
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NoCallClient()
    reply, info = agent.handle(
        agent.new_session(), "pon un temporizador de 10 minutos para el horno"
    )
    assert info is None
    assert agent.client.called is False
    assert llamadas == [{"minutos": 10, "etiqueta": "horno", "tipo": "temporizador"}]
    assert "horno" in reply


def test_handle_inicia_pomodoro(monkeypatch):
    from src.tools import timers

    capturado: dict = {}

    def _fake_iniciar(**k):
        capturado.update(k)
        return {"tipo": "pomodoro", "etiqueta": None, "duracion_min": 25}

    monkeypatch.setattr(timers, "iniciar", _fake_iniciar)
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NoCallClient()
    reply, info = agent.handle(agent.new_session(), "inicia un pomodoro")
    assert info is None
    assert capturado.get("tipo") == "pomodoro"
    assert "Pomodoro" in reply


def test_ajustar_args_estado_temporizador():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    out = agent._ajustar_args([], "cuanto queda del pomodoro")
    assert "consultar_temporizador" in [n for n, _ in out]


def test_ajustar_args_resuelve_evento_por_referencia(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from src import config
    from src.tools import calendar

    monkeypatch.setattr(config.settings, "database", str(tmp_path / "t.db"))
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        dict(config.settings.google_calendar, enabled=False),
    )
    calendar._conn().close()
    calendar.crear_evento("Antiguo", "2020-01-01T10:00")  # id 1
    ev = calendar.crear_evento(
        "Salir a caminar",
        (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes"),
    )  # id 2
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [("cancelar_evento", {"id": 1})]
    out = agent._ajustar_args(parsed, "cancela el evento que ya paso")
    assert dict(out)["cancelar_evento"]["id"] == ev["id"]


def test_ajustar_args_evento_pronombre_usa_ultimos(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from src import config
    from src.tools import calendar

    monkeypatch.setattr(config.settings, "database", str(tmp_path / "t.db"))
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        dict(config.settings.google_calendar, enabled=False),
    )
    calendar._conn().close()
    ev = calendar.crear_evento(
        "Salir a caminar",
        (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes"),
    )
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    session = agent.new_session()
    session.ultimos_eventos = [{"id": ev["id"], "inicio": ev["inicio"]}]
    parsed = [("cancelar_evento", {"id": 999})]
    out = agent._ajustar_args(parsed, "cancelalo", session)
    assert dict(out)["cancelar_evento"]["id"] == ev["id"]


def test_handle_cancela_evento_por_referencia(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from src import config
    from src.tools import calendar

    monkeypatch.setattr(config.settings, "database", str(tmp_path / "t.db"))
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        dict(config.settings.google_calendar, enabled=False),
    )
    calendar._conn().close()
    calendar.crear_evento("Antiguo", "2020-01-01T10:00")  # id 1
    ev = calendar.crear_evento(
        "Salir a caminar",
        (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes"),
    )  # id 2
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NoCallClient()
    s = agent.new_session()
    reply, info = agent.handle(s, "cancela el evento que ya paso")
    assert info == {"type": "confirm"}
    assert s.pending == [("cancelar_evento", {"id": ev["id"]})]
    assert "Salir a caminar" in reply
    assert agent.client.called is False


def test_sanear_args_alias_estado():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    assert agent._sanear_args("listar_tareas", {"pendientes": True}) == {
        "estado": "pendientes"
    }
    assert agent._sanear_args("listar_tareas", {"completadas": True}) == {
        "estado": "completadas"
    }
    assert agent._sanear_args("listar_recordatorios", {"pendientes": True}) == {
        "estado": "pendientes"
    }


def test_sanear_args_descarta_desconocidos():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    out = agent._sanear_args("listar_tareas", {"estado": "todas", "foo": 1, "bar": "x"})
    assert out == {"estado": "todas"}


def test_ajustar_args_normaliza_pendientes():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    out = agent._ajustar_args(
        [("listar_tareas", {"pendientes": True})], "dame las tareas"
    )
    assert out == [("listar_tareas", {"estado": "pendientes"})]


def test_ajustar_args_tareas_completadas():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    out = agent._ajustar_args([("listar_tareas", {})], "que tareas complete")
    assert dict(out)["listar_tareas"]["estado"] == "completadas"


def test_ajustar_args_inyecta_tareas_completadas():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    out = agent._ajustar_args([], "que tareas complete")
    assert dict(out).get("listar_tareas", {}).get("estado") == "completadas"

def test_handle_nombre_ultimo_evento_desde_listado(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from src import config
    from src.tools import calendar

    monkeypatch.setattr(config.settings, "database", str(tmp_path / "t.db"))
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        dict(config.settings.google_calendar, enabled=False),
    )
    calendar._conn().close()
    primero = calendar.crear_evento(
        "Primero", (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")
    )
    ultimo = calendar.crear_evento(
        "Examen Parcial topicos",
        (datetime.now() + timedelta(days=3)).isoformat(timespec="minutes"),
    )
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NoCallClient()
    s = agent.new_session()
    s.ultimos_eventos = [
        {"id": primero["id"], "titulo": primero["titulo"], "inicio": primero["inicio"]},
        {"id": ultimo["id"], "titulo": ultimo["titulo"], "inicio": ultimo["inicio"]},
    ]
    reply, info = agent.handle(s, "dame el nombre completo del ultimo evento")
    assert info is None
    assert "Examen Parcial topicos" in reply
    assert "Primero" not in reply
    assert agent.client.called is False


def test_handle_nombre_ultimo_evento_de_esta_semana(monkeypatch):
    from src.tools import calendar

    eventos = [
        {"id": 2, "titulo": "Segundo", "inicio": "2026-10-20T10:00:00"},
        {"id": 3, "titulo": "Ultimo exacto", "inicio": "2026-10-23T16:40:00"},
    ]
    monkeypatch.setattr(
        calendar, "listar_eventos", lambda **kw: {"total": 2, "eventos": eventos}
    )
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _NoCallClient()
    s = agent.new_session()
    reply, info = agent.handle(s, "dame el nombre del ultimo evento de esta semana")
    assert info is None
    assert "Ultimo exacto" in reply
    assert agent.client.called is False


def test_run_loop_recupera_tool_call_escrita():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": '{"name": "listar_tareas", "arguments": {"estado": "pendientes"}}',
            }
        },
        {"message": {"role": "assistant", "content": "Tienes 2 tareas pendientes."}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    calls = []

    def fake_execute(name, args):
        calls.append((name, args))
        return {"ok": True, "resultado": {"total": 2, "tareas": []}}

    agent._execute = fake_execute
    s = agent.new_session()
    reply, info = agent.handle(s, "dame las tareas pendientes")
    assert reply == "Tienes 2 tareas pendientes."
    assert calls == [("listar_tareas", {"estado": "pendientes"})]
    assert "arguments" not in reply


def test_run_loop_tool_call_textual_de_escritura_pide_confirmacion():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": '{"name": "crear_tarea", "arguments": {"titulo": "Comprar pan"}}',
            }
        }
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    s = agent.new_session()
    reply, info = agent.handle(s, "crea una tarea para comprar pan")
    assert info == {"type": "confirm"}
    assert s.pending == [("crear_tarea", {"titulo": "Comprar pan"})]


def test_run_loop_no_devuelve_codigo():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": '{"name": "inventada", "arguments": {"x": 1}}',
            }
        }
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    s = agent.new_session()
    reply, info = agent.handle(s, "hola")
    assert info is None
    assert "arguments" not in reply
    assert '"name"' not in reply


def test_listar_eventos_guarda_titulo_en_sesion():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "listar_eventos",
                            "arguments": {"periodo": "esta_semana"},
                        }
                    }
                ],
            }
        },
        {"message": {"role": "assistant", "content": "ok"}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    agent._execute = lambda name, args: {
        "ok": True,
        "resultado": {
            "eventos": [
                {"id": 1, "titulo": "Exacto", "inicio": "2026-10-23T16:40:00"}
            ]
        },
    }
    s = agent.new_session()
    agent.handle(s, "eventos de esta semana")
    assert s.ultimos_eventos[0]["titulo"] == "Exacto"

def test_consulta_no_propone_escritura():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "consultar_listas",
                            "arguments": {"accion": "listar"},
                        }
                    },
                    {
                        "function": {
                            "name": "gestionar_listas",
                            "arguments": {
                                "accion": "agregar",
                                "nombre": "Tren de Oti",
                                "texto": "Pelcho",
                            },
                        }
                    },
                ],
            }
        },
        {"message": {"role": "assistant", "content": "Tienes 2 listas."}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    agent._execute = lambda name, args: {"ok": True, "resultado": {"listas": []}}
    s = agent.new_session()
    reply, info = agent.handle(s, "que listas tengo")
    assert info is None
    assert s.pending is None
    assert reply == "Tienes 2 listas."

def test_run_loop_ignora_think_y_reintenta():
    responses = [
        {"message": {"role": "assistant", "content": "<think>razonando</think>"}},
        {"message": {"role": "assistant", "content": "Hola, ¿en qué ayudo?"}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    s = agent.new_session()
    reply, info = agent.handle(s, "hola")
    assert info is None
    assert reply == "Hola, ¿en qué ayudo?"
    assert "think" not in reply

def test_ajustar_args_corrige_anio_inventado():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [
        (
            "crear_evento",
            {
                "titulo": "Examen",
                "inicio": "2023-10-26T10:00",
                "fin": "2023-10-26T12:00",
            },
        )
    ]
    out = agent._ajustar_args(parsed, "crea un evento el 26 de octubre de 10 a 12")
    d = dict(out)["crear_evento"]
    anio = anio_natural(10, 26)
    assert d["inicio"].startswith(f"{anio}-10-26")
    assert d["fin"].startswith(f"{anio}-10-26")


def test_ajustar_args_respeta_anio_explicito():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    parsed = [
        (
            "crear_evento",
            {"titulo": "Examen", "inicio": "2023-10-26T10:00"},
        )
    ]
    out = agent._ajustar_args(
        parsed, "crea un evento el 26 de octubre de 2023 a las 10"
    )
    assert dict(out)["crear_evento"]["inicio"].startswith("2023-10-26")


def test_mixed_read_write_propone_todas_las_escrituras():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "crear_evento",
                            "arguments": {
                                "titulo": "Evento A",
                                "inicio": "2026-10-26T10:00",
                            },
                        }
                    },
                    {
                        "function": {
                            "name": "listar_eventos",
                            "arguments": {},
                        }
                    },
                    {
                        "function": {
                            "name": "crear_evento",
                            "arguments": {
                                "titulo": "Evento B",
                                "inicio": "2026-10-28T14:00",
                            },
                        }
                    },
                ],
            }
        }
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    llamadas: list[str] = []

    def fake_exec(name, args):
        llamadas.append(name)
        if name == "listar_eventos":
            return {"ok": True, "resultado": {"total": 0, "eventos": []}}
        return {"ok": True, "resultado": {"id": 1, **args}}

    agent._execute = fake_exec
    s = agent.new_session()
    reply, info = agent.handle(s, "crea dos eventos y muestrame los eventos")

    assert info == {"type": "confirm"}
    assert [n for n, _ in s.pending] == ["crear_evento", "crear_evento"]
    assert llamadas == ["listar_eventos"]  # las escrituras aun no se ejecutan
    assert "Evento A" in reply and "Evento B" in reply

    # Historial: assistant(lectura), tool(lectura), assistant(escrituras).
    idx_user = max(
        i for i, m in enumerate(s.messages) if m.get("role") == "user"
    )
    cola = s.messages[idx_user + 1 :]
    assert cola[0]["role"] == "assistant"
    assert [tc["function"]["name"] for tc in cola[0]["tool_calls"]] == [
        "listar_eventos"
    ]
    assert cola[1]["role"] == "tool"
    assert cola[1]["tool_name"] == "listar_eventos"
    assert cola[2]["role"] == "assistant"
    assert [tc["function"]["name"] for tc in cola[2]["tool_calls"]] == [
        "crear_evento",
        "crear_evento",
    ]


def test_confirmacion_permite_proponer_la_accion_que_falta():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "crear_evento",
                            "arguments": {
                                "titulo": "Evento B",
                                "inicio": "2026-10-28T14:00",
                            },
                        }
                    }
                ],
            }
        },
        {"message": {"role": "assistant", "content": "Listo, cree los dos eventos."}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(responses)
    ejecutadas: list[tuple[str, dict]] = []

    def fake_exec(name, args):
        ejecutadas.append((name, args))
        return {"ok": True, "resultado": {"id": len(ejecutadas), **args}}

    agent._execute = fake_exec
    s = agent.new_session()
    primero = {"titulo": "Evento A", "inicio": "2026-10-26T10:00"}
    s.pending = [("crear_evento", primero)]
    s.messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "crear_evento", "arguments": primero}}
            ],
        }
    )

    reply, info = agent.handle(s, "si")
    assert [n for n, _ in ejecutadas] == ["crear_evento"]
    assert info == {"type": "confirm"}
    assert s.pending is not None
    assert s.pending[0][1]["titulo"] == "Evento B"

    reply2, info2 = agent.handle(s, "si")
    assert info2 is None
    assert [a.get("titulo") for n, a in ejecutadas if n == "crear_evento"] == [
        "Evento A",
        "Evento B",
    ]


def test_cancelar_pending_anota_un_resultado_por_accion():
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    agent.client = _ScriptClient(
        [{"message": {"role": "assistant", "content": "Cancelado."}}]
    )
    s = agent.new_session()
    s.pending = [
        ("crear_evento", {"titulo": "A", "inicio": "2026-10-26T10:00"}),
        ("crear_evento", {"titulo": "B", "inicio": "2026-10-28T14:00"}),
    ]
    s.messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": n, "arguments": a}} for n, a in s.pending
            ],
        }
    )

    reply, info = agent.handle(s, "no")
    assert info is None
    tools = [m for m in s.messages if m.get("role") == "tool"]
    assert len(tools) == 2
    assert all(m.get("tool_name") == "crear_evento" for m in tools)

class _CaptureScript:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_call_solo_tools_del_dominio():
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "listar_tareas",
                            "arguments": {},
                        }
                    }
                ],
            }
        },
        {"message": {"role": "assistant", "content": "Tienes 0 tareas."}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    client = _CaptureScript(responses)
    agent.client = client
    agent._execute = lambda name, args: {
        "ok": True,
        "resultado": {"total": 0, "tareas": []},
    }
    reply, info = agent.handle(agent.new_session(), "que tareas tengo")
    assert reply == "Tienes 0 tareas."
    names = {t["function"]["name"] for t in client.calls[0]["tools"]}
    assert "listar_tareas" in names
    assert "enviar_email" not in names
    assert "crear_evento" not in names


def test_fallback_full_tools():
    responses = [
        {"message": {"role": "assistant", "content": "No se."}},
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "listar_tareas",
                            "arguments": {},
                        }
                    }
                ],
            }
        },
        {"message": {"role": "assistant", "content": "Tienes 0 tareas."}},
    ]
    agent = Agent(_registry(), model="dummy", system_prompt="sys")
    client = _CaptureScript(responses)
    agent.client = client
    agent._execute = lambda name, args: {
        "ok": True,
        "resultado": {"total": 0, "tareas": []},
    }
    agent.handle(agent.new_session(), "que tareas tengo")
    assert len(client.calls[1]["tools"]) == len(agent.registry.schemas())
    assert len(client.calls[1]["tools"]) > len(client.calls[0]["tools"])


def test_recortar_presupuesto_conserva_sistemas():
    agent = Agent(
        _registry(),
        model="dummy",
        system_prompt="sys",
        num_ctx=4096,
        num_predict=200,
    )
    s = agent.new_session()
    s.messages.append({"role": "system", "content": "RESUMEN"})
    for i in range(20):
        s.messages.append({"role": "user", "content": "x" * 2000})
        s.messages.append({"role": "assistant", "content": "y" * 2000})
    esquemas = agent.registry.schemas({"core"})
    antes = agent._estimar_tokens(s.messages, esquemas)
    agent._recortar_presupuesto(s, esquemas)
    despues = agent._estimar_tokens(s.messages, esquemas)
    assert despues < antes
    assert despues <= 4096 - 200 - 400
    assert s.messages[0]["content"] == "sys"
    assert s.messages[1]["content"] == "RESUMEN"


def test_persistencia_sesion(tmp_path):
    from src.brain.memory import SessionStore

    store = SessionStore(str(tmp_path / "mem.db"))
    agent = Agent(
        _registry(),
        model="dummy",
        system_prompt="sys",
        store=store,
        memory={
            "enabled": True,
            "history_limit": 16,
            "summary_after": 100,
            "facts_limit": 20,
        },
    )
    agent.client = _ScriptClient(
        [{"message": {"role": "assistant", "content": "Hola!"}}]
    )
    s = agent.new_session(session_id="web-1", canal="web")
    agent.handle(s, "hola")
    s2 = agent.new_session(session_id="web-1", canal="web")
    contenidos = [m.get("content") for m in s2.messages]
    assert "hola" in contenidos
    assert "Hola!" in contenidos


def test_pending_persistido(tmp_path):
    from src.brain.memory import SessionStore

    store = SessionStore(str(tmp_path / "mem.db"))
    agent = Agent(
        _registry(),
        model="dummy",
        system_prompt="sys",
        store=store,
        memory={
            "enabled": True,
            "history_limit": 16,
            "summary_after": 100,
            "facts_limit": 20,
        },
    )
    agent.client = _ScriptClient(
        [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "crear_evento",
                                "arguments": {
                                    "titulo": "Examen",
                                    "inicio": "2026-10-28T10:00",
                                },
                            }
                        }
                    ],
                }
            }
        ]
    )
    s = agent.new_session(session_id="tg-1", canal="telegram")
    reply, info = agent.handle(s, "crea un evento el 28 de octubre a las 10")
    assert info == {"type": "confirm"}

    s2 = agent.new_session(session_id="tg-1", canal="telegram")
    assert s2.pending is not None
    assert s2.pending[0][0] == "crear_evento"
    assert s2.messages[-1].get("tool_calls")

    ejecutadas = []

    def fake_exec(name, args):
        ejecutadas.append((name, args))
        return {"ok": True, "resultado": {"id": 1, **args}}

    agent._execute = fake_exec
    agent.client = _ScriptClient(
        [{"message": {"role": "assistant", "content": "Evento creado."}}]
    )
    reply2, info2 = agent.handle(s2, "si")
    assert info2 is None
    assert ejecutadas and ejecutadas[0][0] == "crear_evento"


def test_recuerda_y_olvida(tmp_path):
    from src.brain.memory import SessionStore

    store = SessionStore(str(tmp_path / "mem.db"))
    agent = Agent(
        _registry(),
        model="dummy",
        system_prompt="sys",
        store=store,
        memory={
            "enabled": True,
            "history_limit": 16,
            "summary_after": 100,
            "facts_limit": 20,
        },
    )
    s = agent.new_session(session_id="m-1", canal="web")
    r, _ = agent.handle(s, "recuerda que me gusta el cafe")
    assert "recordare" in r.lower()
    assert [f["valor"] for f in store.list_facts()] == ["me gusta el cafe"]

    r2, _ = agent.handle(s, "/memoria")
    assert "cafe" in r2

    agent.handle(s, "/olvida cafe")
    assert store.list_facts() == []


def test_trim_conserva_resumen_y_hechos():
    agent = Agent(
        _registry(), model="dummy", system_prompt="sys", history_limit=2
    )
    s = agent.new_session()
    s.messages += [
        {"role": "system", "content": "RESUMEN"},
        {"role": "system", "content": "HECHOS"},
    ]
    for i in range(6):
        s.messages.append({"role": "user", "content": f"u{i}"})
        s.messages.append({"role": "assistant", "content": f"a{i}"})
    agent._trim(s)
    contenidos = [m.get("content") for m in s.messages]
    assert "RESUMEN" in contenidos
    assert "HECHOS" in contenidos

def test_resumen_automatico(tmp_path):
    from src.brain.memory import SessionStore

    store = SessionStore(str(tmp_path / "mem.db"))
    agent = Agent(
        _registry(),
        model="dummy",
        system_prompt="sys",
        store=store,
        memory={
            "enabled": True,
            "history_limit": 2,
            "summary_after": 4,
            "facts_limit": 20,
        },
    )
    agent.client = _ScriptClient(
        [
            {"message": {"role": "assistant", "content": f"respuesta {i}"}}
            for i in range(6)
        ]
    )
    agent._resumir = lambda previo, texto: "RESUMEN NUEVO"
    s = agent.new_session(session_id="sum-1", canal="web")
    for i in range(5):
        agent.handle(s, f"mensaje {i}")

    s2 = agent.new_session(session_id="sum-1", canal="web")
    assert s2.resumen == "RESUMEN NUEVO"
    assert any(
        "RESUMEN NUEVO" in (m.get("content") or "") for m in s2.messages
    )
