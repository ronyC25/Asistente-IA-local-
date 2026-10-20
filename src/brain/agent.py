"""Loop principal del agente (tool-calling + confirmacion)."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import ollama

log = logging.getLogger("asistente.agent")

from .capabilities import texto_capacidades
from .confirm import (
    build_proposal,
    buscar_termino_de_texto,
    classify_confirmation,
    dominio_lectura,
    es_cancelacion,
    es_referencia_objeto,
    estado_tareas_de_texto,
    etiqueta_de_texto,
    fecha_de_texto,
    intencion_temporizador,
    looks_like_action,
    looks_like_query,
    orden_de_texto,
    periodo_de_texto,
    pregunta_capacidades,
    pregunta_cuanto_falta,
    pregunta_nombre_evento,
    quiere_historial_recordatorios,
    quiere_proximo,
    quiere_eventos_pasados,
    rango_de_texto,
    referencia_evento,
)
from .registry import Registry
from .textfmt import strip_think
from .tooltext import extraer_llamadas, parece_llamada


class Session:
    def __init__(self, system_prompt: str) -> None:
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self.pending: list[tuple[str, dict]] | None = None
        self.ultimos_eventos: list[dict] = []


def _norm_args(args: Any) -> dict:
    if args is None:
        return {}
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {}
    return dict(args)


# Herramientas de listado que aceptan el parametro 'periodo' (rango relativo).
_TOOLS_CON_PERIODO = (
    "listar_eventos",
    "listar_tareas",
    "listar_recordatorios",
    "consultar_notas",
)

# Dominio de datos -> herramienta de lectura por defecto (fallback determinista).
_DOMINIO_TOOL = {
    "tareas": "listar_tareas",
    "recordatorios": "listar_recordatorios",
    "notas": "consultar_notas",
    "listas": "consultar_listas",
    "eventos": "listar_eventos",
    "email": "leer_email",
    "busqueda": "buscar_todo",
    "temporizadores": "consultar_temporizador",
}

# Herramientas de listado que aceptan el filtro 'etiqueta'.
_TOOLS_CON_ETIQUETA = (
    "listar_tareas",
    "listar_recordatorios",
    "consultar_notas",
    "listar_eventos",
)

# El modelo a veces pasa el estado como flag (pendientes=True); se mapea a 'estado'.
_ALIAS_ESTADO = {
    "pendientes": "pendientes",
    "pendiente": "pendientes",
    "completadas": "completadas",
    "completada": "completadas",
    "todas": "todas",
    "todos": "todas",
}


def _fechas_de_texto(user_text: str) -> dict:
    """Argumentos de fecha (periodo/dias o desde/hasta) resueltos en codigo."""
    periodo = periodo_de_texto(user_text)
    if periodo:
        p, n = periodo
        d: dict = {"periodo": p}
        if n is not None:
            d["dias"] = n
        return d
    f = fecha_de_texto(user_text)
    if f:
        return {"desde": f.isoformat(), "hasta": f.isoformat()}
    r = rango_de_texto(user_text)
    if r:
        return {"desde": r[0].isoformat(), "hasta": r[1].isoformat()}
    return {}


def _merge_fechas(args: dict, fechas: dict) -> dict:
    if not fechas:
        return args
    if "periodo" in fechas:
        args["periodo"] = fechas["periodo"]
        if "dias" in fechas:
            args["dias"] = fechas["dias"]
        args.pop("desde", None)
        args.pop("hasta", None)
    else:
        args["desde"] = fechas["desde"]
        args["hasta"] = fechas["hasta"]
        args.pop("periodo", None)
        args.pop("dias", None)
    return args


def _args_dominio(dominio: str, user_text: str | None) -> dict:
    """Argumentos por defecto para la lectura forzada de un dominio."""
    txt = user_text or ""
    t = txt.lower()
    if dominio == "tareas":
        est_txt = estado_tareas_de_texto(txt)
        if est_txt:
            args = {"estado": est_txt}
        elif any(w in t for w in ("todas", "todos", "base de datos")):
            args = {"estado": "todas"}
        else:
            args = {}
    elif dominio == "recordatorios":
        args = {"estado": "historial" if quiere_historial_recordatorios(txt) else "pendientes"}
    elif dominio == "notas":
        args = {"accion": "listar"}
    elif dominio == "listas":
        args = {"accion": "listar"}
    elif dominio == "busqueda":
        args = {"texto": buscar_termino_de_texto(txt) or txt}
    elif dominio == "temporizadores":
        args = {}
    else:
        args = {}

    if dominio == "notas" and orden_de_texto(txt) == "antiguas":
        args["orden"] = "antiguas"
        args["limite"] = 1
    if dominio == "eventos":
        if orden_de_texto(txt) == "antiguas":
            args["orden"] = "antiguos"
            args["limite"] = 1

    if dominio in ("tareas", "recordatorios", "notas", "eventos"):
        fechas = _fechas_de_texto(txt)
        _merge_fechas(args, fechas)
        etq = etiqueta_de_texto(txt)
        if etq:
            args.setdefault("etiqueta", etq)
        if dominio == "eventos" and "periodo" not in fechas and (
            quiere_proximo(txt) or pregunta_cuanto_falta(txt)
        ):
            args.setdefault("limite", 1)
    return args


def partition_calls(
    parsed: list[tuple[str, dict]], registry: Registry
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """Separa las llamadas en (lecturas, escrituras) segun el tipo de tool."""
    reads: list[tuple[str, dict]] = []
    writes: list[tuple[str, dict]] = []
    for name, args in parsed:
        tool = registry.get(name)
        if tool is not None and tool.kind == "write":
            writes.append((name, args))
        else:
            reads.append((name, args))
    return reads, writes


class Agent:
    def __init__(
        self,
        registry: Registry,
        model: str,
        system_prompt: str,
        temperature: float = 0.25,
        max_iters: int = 6,
        num_ctx: int = 4096,
        num_predict: int = 400,
        keep_alive: str | int | None = "30m",
        history_limit: int = 16,
        host: str | None = None,
    ) -> None:
        self.registry = registry
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_iters = max_iters
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.keep_alive = keep_alive
        self.history_limit = history_limit
        self.client = ollama.Client(host=host) if host else ollama.Client()
        self._tool_names = set(registry.names())

    def new_session(self) -> Session:
        return Session(self.system_prompt)

    def _call(self, session: Session, think: bool = False, with_tools: bool = True) -> dict:
        options: dict = {"temperature": self.temperature, "num_ctx": self.num_ctx}
        if self.num_predict:
            options["num_predict"] = self.num_predict
        kwargs: dict = {
            "model": self.model,
            "messages": session.messages,
            "options": options,
            "think": think,
        }
        if with_tools:
            kwargs["tools"] = self.registry.schemas()
        if self.keep_alive is not None:
            kwargs["keep_alive"] = self.keep_alive
        return self.client.chat(**kwargs)

    def _sanear_args(self, name: str, args: dict) -> dict:
        """Normaliza alias y descarta parametros que no existen en el schema.

        El modelo a veces inventa parametros (p. ej. ``listar_tareas(pendientes=True)``);
        los mapeamos a ``estado`` o los descartamos para no romper con ``TypeError``.
        """
        tool = self.registry.get(name)
        if tool is None:
            return dict(args or {})
        props = set(
            (tool.schema.get("function", {}).get("parameters", {}) or {}).get(
                "properties", {}
            )
        )
        out = dict(args or {})
        if "estado" in props:
            for k in list(out.keys()):
                if k in _ALIAS_ESTADO and out[k]:
                    out["estado"] = _ALIAS_ESTADO[k]
                    del out[k]
        for k in list(out.keys()):
            if k not in props:
                log.debug("descarto parametro desconocido: %s.%s", name, k)
                del out[k]
        return out

    def _ajustar_args(
        self,
        parsed: list[tuple[str, dict]],
        user_text: str | None,
        session: Session | None = None,
    ) -> list[tuple[str, dict]]:
        """Ajustes deterministas de argumentos, para no depender del modelo:

        - historial de recordatorios (estado por defecto -> 'historial');
        - rangos de fecha relativos (fija 'periodo' y descarta desde/hasta).
        """
        parsed = [(n, self._sanear_args(n, dict(a or {}))) for n, a in parsed]
        if not user_text:
            return parsed
        fechas = _fechas_de_texto(user_text)
        orden = orden_de_texto(user_text)
        proximo = quiere_proximo(user_text)
        falta = pregunta_cuanto_falta(user_text)
        etiqueta = etiqueta_de_texto(user_text)
        ajustado: list[tuple[str, dict]] = []
        for name, args in parsed:
            args = dict(args or {})
            if name == "listar_recordatorios":
                est = str(args.get("estado", "")).strip().lower()
                if est in ("", "pendiente", "pendientes", "todos", "todas") and (
                    quiere_historial_recordatorios(user_text)
                ):
                    args["estado"] = "historial"
            if name in _TOOLS_CON_PERIODO and fechas:
                _merge_fechas(args, fechas)
            if name in _TOOLS_CON_ETIQUETA and etiqueta and not args.get("etiqueta"):
                args["etiqueta"] = etiqueta
            if name == "listar_tareas":
                est_txt = estado_tareas_de_texto(user_text)
                if est_txt:
                    args["estado"] = est_txt
            if orden and name == "consultar_notas":
                args["orden"] = "antiguas" if orden == "antiguas" else "recientes"
                if orden == "antiguas":
                    args.setdefault("limite", 1)
            if name == "listar_eventos":
                if orden == "antiguas":
                    args["orden"] = "antiguos"
                    args.setdefault("limite", 1)
                if quiere_eventos_pasados(user_text):
                    args["pasados"] = True
                if (proximo or falta) and not fechas:
                    # "el proximo evento" / "cuanto falta" = sin rango de fechas:
                    # no dejar un 'periodo' inventado por el modelo (rompia la
                    # consulta cuando no habia eventos en ese rango).
                    args.pop("periodo", None)
                    args.pop("dias", None)
                    args.setdefault("limite", 1)
            if name == "listar_recordatorios" and falta:
                args.setdefault("limite", 1)
            ajustado.append((name, args))
        # Inyeccion determinista: si es una consulta de un dominio claro y el
        # modelo no llamo la herramienta de lectura de ese dominio, la anadimos
        # (evita que confunda p. ej. 'notificaciones' con notas o no llame nada).
        if looks_like_query(user_text) and not looks_like_action(user_text):
            dominio = dominio_lectura(user_text)
            if dominio:
                tool_name = _DOMINIO_TOOL[dominio]
                if tool_name not in {n for n, _ in ajustado}:
                    ajustado.append((tool_name, _args_dominio(dominio, user_text)))
        # Cancelar/editar evento: resolver el id por referencia temporal (el
        # modelo a veces elige un id equivocado, p. ej. cancelar "Mi cumpleaños").
        if any(n in ("cancelar_evento", "editar_evento") for n, _ in ajustado):
            from ..tools import calendar

            elegido = None
            ref = referencia_evento(user_text)
            if ref:
                ev = calendar.resolver_evento(ref)
                if ev:
                    elegido = ev
            elif (
                es_referencia_objeto(user_text)
                and session is not None
                and session.ultimos_eventos
            ):
                cands = session.ultimos_eventos
                pasados = [
                    e
                    for e in cands
                    if e.get("inicio")
                    and datetime.fromisoformat(e["inicio"]) < datetime.now()
                ]
                if len(cands) == 1:
                    elegido = cands[0]
                elif len(pasados) == 1:
                    elegido = pasados[0]
            if elegido and elegido.get("id") is not None:
                ajustado = [
                    (
                        name,
                        {**(args or {}), "id": elegido["id"]},
                    )
                    if name in ("cancelar_evento", "editar_evento")
                    else (name, args)
                    for name, args in ajustado
                ]
        return ajustado

    def _trim(self, session: Session) -> None:
        """Recorta el historial: conserva el system (idx 0) y los ultimos
        ``history_limit`` mensajes. Descarta los mensajes ``tool`` iniciales que
        quedarian huerfanos (sin su ``assistant(tool_calls)`` previo)."""
        limit = self.history_limit
        if limit <= 0 or len(session.messages) <= limit + 1:
            return
        system = session.messages[0]
        keep = session.messages[1:][-limit:]
        while keep and keep[0].get("role") == "tool":
            keep = keep[1:]
        session.messages = [system] + keep

    def _execute(self, name: str, args: dict) -> dict:
        tool = self.registry.get(name)
        if tool is None:
            return {"ok": False, "error": f"herramienta desconocida: {name}"}
        args = self._sanear_args(name, dict(args or {}))
        try:
            return {"ok": True, "resultado": tool.run(args)}
        except Exception as exc:  # noqa: BLE001 - se devuelve al modelo
            return {"ok": False, "error": str(exc)}

    def handle(self, session: Session, user_text: str) -> tuple[str, dict | None]:
        """Procesa un mensaje. Devuelve (respuesta, pending_info|None)."""
        if session.pending is not None:
            decision = classify_confirmation(user_text)
            if decision is None:
                resumen = build_proposal(session.pending, self.registry)
                return (
                    "Sigo esperando tu confirmacion. Tienes una accion pendiente:\n\n"
                    f"{resumen}",
                    {"type": "confirm"},
                )
            pending = session.pending
            session.pending = None
            if decision is True:
                for name, args in pending:
                    result = self._execute(name, args)
                    session.messages.append(
                        {"role": "tool", "content": json.dumps(result, ensure_ascii=False)}
                    )
                session.messages.append(
                    {
                        "role": "system",
                        "content": (
                            "La accion ya se ejecuto. Resume el resultado al usuario "
                            "en una frase, sin volver a llamar ninguna herramienta."
                        ),
                    }
                )
            else:
                session.messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {"ok": False, "resultado": "El usuario canceló la acción."},
                            ensure_ascii=False,
                        ),
                    }
                )
            return self._run_loop(session)

        # Preguntas sobre capacidades/ayuda: respuesta determinista y completa
        # (no pasa por el LLM, asi nunca se trunca por el limite de tokens).
        if pregunta_capacidades(user_text):
            respuesta = texto_capacidades(self.registry)
            session.messages.append({"role": "user", "content": user_text})
            session.messages.append({"role": "assistant", "content": respuesta})
            return respuesta, None

        # Temporizadores/Pomodoro: iniciar/cancelar de forma determinista e
        # instantanea (sin confirmacion ni depender del modelo).
        intent = intencion_temporizador(user_text)
        if intent:
            return self._manejar_temporizador(intent, session, user_text), None

        # Cancelar un EVENTO por referencia temporal ("el que ya paso", "el de
        # hoy", "cancelalo"): resolver el id de forma determinista (el modelo a
        # veces no llama la herramienta o elige el evento equivocado).
        if es_cancelacion(user_text):
            from ..tools import calendar

            ev = None
            ref = referencia_evento(user_text)
            if ref and dominio_lectura(user_text) == "eventos":
                ev = calendar.resolver_evento(ref)
            elif es_referencia_objeto(user_text) and session.ultimos_eventos:
                cands = session.ultimos_eventos
                pasados = [
                    e
                    for e in cands
                    if e.get("inicio")
                    and datetime.fromisoformat(e["inicio"]) < datetime.now()
                ]
                elegido = (
                    cands[0]
                    if len(cands) == 1
                    else (pasados[0] if len(pasados) == 1 else None)
                )
                if elegido and elegido.get("id") is not None:
                    ev = calendar.obtener_evento(elegido["id"])
            if ev and ev.get("estado") == "activo":
                session.pending = [("cancelar_evento", {"id": ev["id"]})]
                return (
                    build_proposal(session.pending, self.registry),
                    {"type": "confirm"},
                )

        # "¿Cuál es el nombre completo del último evento?" -> respuesta exacta y
        # determinista. El modelo parafraseaba el título y elegía el más viejo.
        if pregunta_nombre_evento(user_text):
            respuesta = self._describir_evento_solicitado(session, user_text)
            if respuesta:
                session.messages.append({"role": "user", "content": user_text})
                session.messages.append({"role": "assistant", "content": respuesta})
                return respuesta, None

        self._trim(session)
        session.messages.append({"role": "user", "content": user_text})
        return self._run_loop(session, user_text=user_text)

    def _manejar_temporizador(
        self, intent: dict, session: Session, user_text: str
    ) -> str:
        from ..config import settings
        from ..tools import timers

        try:
            accion = intent["accion"]
            if accion == "iniciar":
                t = timers.iniciar(
                    minutos=intent.get("minutos"),
                    etiqueta=intent.get("etiqueta"),
                    tipo=intent.get("tipo") or "temporizador",
                )
                etq = f" «{t['etiqueta']}»" if t.get("etiqueta") else ""
                if t.get("tipo") == "pomodoro":
                    cfg = settings.pomodoro
                    msg = (
                        f"Pomodoro{etq} iniciado: {t['duracion_min']} min de trabajo "
                        f"y {cfg['descanso_min']} de descanso."
                    )
                else:
                    msg = f"Temporizador{etq} iniciado: {t['duracion_min']} minutos."
            elif accion == "pausar":
                c = timers.pausar(id=intent.get("id"), etiqueta=intent.get("etiqueta"))
                etq = f" «{c['etiqueta']}»" if c.get("etiqueta") else ""
                msg = f"Temporizador{etq} pausado."
            elif accion == "reanudar":
                c = timers.reanudar(id=intent.get("id"), etiqueta=intent.get("etiqueta"))
                etq = f" «{c['etiqueta']}»" if c.get("etiqueta") else ""
                msg = f"Temporizador{etq} reanudado."
            else:
                c = timers.cancelar(id=intent.get("id"), etiqueta=intent.get("etiqueta"))
                etq = f" «{c['etiqueta']}»" if c.get("etiqueta") else ""
                msg = f"Temporizador{etq} cancelado."
        except Exception as exc:  # noqa: BLE001
            msg = f"No pude gestionar el temporizador: {exc}"
        session.messages.append({"role": "user", "content": user_text})
        session.messages.append({"role": "assistant", "content": msg})
        return msg

    def _describir_evento_solicitado(
        self, session: Session, user_text: str
    ) -> str | None:
        """Resuelve en codigo el evento pedido y devuelve su titulo EXACTO."""
        from ..tools import calendar

        ref = referencia_evento(user_text)
        periodo = periodo_de_texto(user_text)
        if periodo:
            p, n = periodo
            try:
                res = calendar.listar_eventos(
                    periodo=p,
                    dias=n,
                    pasados=ref != "proximo",
                    limite=100,
                )
            except ValueError:
                return None
            eventos = res.get("eventos") or []
            if not eventos:
                etiqueta = str(p).replace("_", " ")
                return f"No encontre eventos en ese periodo ({etiqueta})."
            if ref in ("antiguo", "proximo"):
                ev = min(eventos, key=lambda e: e.get("inicio") or "")
            else:
                ev = max(eventos, key=lambda e: e.get("inicio") or "")
            session.ultimos_eventos = [
                {
                    "id": e.get("id"),
                    "titulo": e.get("titulo"),
                    "inicio": e.get("inicio"),
                }
                for e in eventos
            ]
            return self._texto_evento(ev, ref)

        if session.ultimos_eventos:
            candidatos = session.ultimos_eventos
            if ref == "antiguo":
                elegido = min(candidatos, key=lambda e: e.get("inicio") or "")
            elif ref == "proximo":
                ahora = datetime.now()
                futuros = [
                    e
                    for e in candidatos
                    if e.get("inicio")
                    and datetime.fromisoformat(e["inicio"]) >= ahora
                ]
                if not futuros:
                    ev = calendar.resolver_evento("proximo")
                    if not ev:
                        return "No hay proximos eventos."
                    return self._texto_evento(ev, "proximo")
                elegido = min(futuros, key=lambda e: e.get("inicio") or "")
            else:
                elegido = max(candidatos, key=lambda e: e.get("inicio") or "")
            ev = (
                calendar.obtener_evento(elegido["id"])
                if elegido.get("id") is not None
                else None
            ) or elegido
        else:
            ev = calendar.resolver_evento(ref or "ultimo_pasado")

        if not ev:
            return "No encontre ningun evento para esa referencia."
        return self._texto_evento(ev, ref)

    @staticmethod
    def _texto_evento(ev: dict, ref: str | None = None) -> str:
        titulo = ev.get("titulo") or "(sin titulo)"
        inicio = ev.get("inicio")
        cuando = ""
        if inicio:
            try:
                dt = datetime.fromisoformat(str(inicio))
                cuando = f" ({dt.strftime('%d/%m/%Y %H:%M')})"
            except (ValueError, TypeError):
                cuando = f" ({inicio})"
        if ref == "antiguo":
            prefijo = "El primer evento"
        elif ref == "proximo":
            prefijo = "El proximo evento"
        elif ref:
            prefijo = "El ultimo evento"
        else:
            prefijo = "El evento"
        return f'{prefijo} es "{titulo}"{cuando}.'

    _NUDGE = (
        "IMPORTANTE: SI tienes la capacidad de enviar por Telegram/email y de crear, "
        "agendar, editar, cancelar o exportar mediante herramientas. El usuario pidio "
        "una ACCION pero no llamaste ninguna herramienta de escritura y solo "
        "respondiste con texto. Llama AHORA a la herramienta adecuada (por ejemplo "
        "enviar_telegram, enviar_email, crear_tarea, crear_evento, crear_recordatorio, "
        "exportar_ics) con los datos reales. NO respondas que no puedes: puedes "
        "hacerlo usando la herramienta."
    )

    _NUDGE_READ = (
        "IMPORTANTE: el usuario te pidio CONSULTAR datos y NO llamaste ninguna "
        "herramienta de lectura. Tienes acceso a TODOS los datos locales. Llama "
        "AHORA a la herramienta adecuada: listar_tareas, listar_recordatorios "
        "(= 'notificaciones'/'avisos'), consultar_notas, consultar_listas, "
        "listar_eventos o leer_email. Responde con los datos reales que devuelva. "
        "Nunca digas que no tienes acceso."
    )

    def _run_loop(
        self,
        session: Session,
        user_text: str | None = None,
        stage: int = 0,
        think: bool = False,
        retry_empty: bool = True,
    ) -> tuple[str, dict | None]:
        saw_write = False
        saw_tool = False
        seen_reads: set = set()
        # Preguntas de capacidades/ayuda: no insistir con herramientas de lectura.
        es_meta = bool(user_text) and pregunta_capacidades(user_text)
        for _ in range(self.max_iters):
            response = self._call(session, think=think)
            message = response.get("message", {}) or {}
            tool_calls = message.get("tool_calls") or []

            # El modelo a veces escribe la llamada como texto (JSON). La
            # recuperamos y seguimos el flujo normal (lecturas/escrituras).
            if not tool_calls:
                content = strip_think(message.get("content") or "")
                llamadas = extraer_llamadas(content, self._tool_names)
                if llamadas:
                    log.info(
                        "recuperada llamada escrita como texto: %s",
                        [n for n, _ in llamadas],
                    )
                    tool_calls = [
                        {"function": {"name": nombre, "arguments": args}}
                        for nombre, args in llamadas
                    ]
                    message = {"content": "", "tool_calls": tool_calls}

            if not tool_calls:
                content = strip_think(message.get("content") or "")
                nudge: str | None = None
                if user_text and stage < 2 and not es_meta:
                    if looks_like_action(user_text) and not saw_write:
                        nudge = self._NUDGE
                    elif (
                        looks_like_query(user_text)
                        and not saw_tool
                        and not looks_like_action(user_text)
                    ):
                        nudge = self._NUDGE_READ
                if nudge is not None:
                    session.messages.append({"role": "system", "content": nudge})
                    # 1er reintento sin pensar; 2º (si el nudge no basto) con thinking.
                    return self._run_loop(
                        session,
                        user_text=user_text,
                        stage=stage + 1,
                        think=stage == 1,
                    )
                # Fallback determinista: si tras los reintentos el modelo no llamo
                # ninguna herramienta pero la consulta es de un dominio claro,
                # ejecutamos la lectura nosotros y le pedimos que la resuma.
                if (
                    user_text
                    and stage >= 1
                    and not saw_tool
                    and not es_meta
                    and looks_like_query(user_text)
                    and not looks_like_action(user_text)
                ):
                    dominio = dominio_lectura(user_text)
                    if dominio:
                        name = _DOMINIO_TOOL[dominio]
                        args = _args_dominio(dominio, user_text)
                        result = self._execute(name, args)
                        session.messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "Datos reales de la consulta (JSON): "
                                    + json.dumps(result, ensure_ascii=False)
                                    + ". Resume en lenguaje natural para el usuario."
                                ),
                            }
                        )
                        return self._run_loop(
                            session, user_text=None, stage=stage + 1, think=False
                        )
                # El modelo a veces devuelve contenido vacio o solo un bloque
                # <think>: pedimos el resumen SIN herramientas (asi no inventa
                # otras llamadas) y sin razonamiento.
                if not content.strip() and retry_empty:
                    session.messages.append(
                        {
                            "role": "system",
                            "content": (
                                "Responde al usuario en lenguaje natural usando SOLO "
                                "los datos de las herramientas anteriores. No escribas "
                                "<think> ni razonamiento y no llames mas herramientas."
                            ),
                        }
                    )
                    resp = self._call(session, think=False, with_tools=False)
                    content = strip_think(
                        (resp.get("message") or {}).get("content") or ""
                    )
                if not content.strip():
                    content = (
                        "No pude generar una respuesta. ¿Puedes repetir la pregunta?"
                    )
                if parece_llamada(content):
                    content = (
                        "No pude interpretar esa solicitud. ¿Puedes repetirla "
                        "o expresarla de otra forma?"
                    )
                session.messages.append({"role": "assistant", "content": content})
                return content, None

            saw_tool = True
            parsed: list[tuple[str, dict]] = [
                (tc["function"]["name"], _norm_args(tc["function"].get("arguments")))
                for tc in tool_calls
            ]
            parsed = self._ajustar_args(parsed, user_text, session)
            reads, writes = partition_calls(parsed, self.registry)

            # Una CONSULTA pura no debe proponer escrituras: el modelo a veces
            # "agrega" un dato que acaba de leer (p. ej. "que listas tengo").
            if (
                user_text
                and looks_like_query(user_text)
                and not looks_like_action(user_text)
                and writes
            ):
                log.info(
                    "ignoro escrituras en una consulta: %s",
                    [n for n, _ in writes],
                )
                if not reads:
                    dominio = dominio_lectura(user_text)
                    if dominio:
                        reads = [
                            (
                                _DOMINIO_TOOL[dominio],
                                _args_dominio(dominio, user_text),
                            )
                        ]
                writes = []
                parsed = reads

            assistant_msg = {
                "role": "assistant",
                "content": strip_think(message.get("content") or ""),
                "tool_calls": [
                    {"function": {"name": n, "arguments": a}} for n, a in parsed
                ],
            }
            session.messages.append(assistant_msg)

            if writes and not reads:
                saw_write = True
                session.pending = writes
                return build_proposal(writes, self.registry), {"type": "confirm"}

            # Cortador de bucle: si el modelo vuelve a pedir SOLO lecturas que ya
            # ejecutamos en este turno, dejamos de llamar herramientas y forzamos
            # un resumen (evita "demasiados pasos" en sesiones largas).
            nuevas = [
                (n, a)
                for (n, a) in reads
                if (n, json.dumps(a, sort_keys=True)) not in seen_reads
            ]
            if reads and not nuevas and not writes:
                session.messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Ya tienes los datos de esas herramientas. Responde "
                            "ahora al usuario en lenguaje natural, sin volver a "
                            "llamar ninguna herramienta."
                        ),
                    }
                )
                resp = self._call(session, think=False, with_tools=False)
                content = strip_think((resp.get("message") or {}).get("content") or "")
                if not content.strip():
                    content = (
                        "No pude generar una respuesta. ¿Puedes repetir la pregunta?"
                    )
                if parece_llamada(content):
                    content = (
                        "No pude interpretar esa solicitud. ¿Puedes repetirla "
                        "o expresarla de otra forma?"
                    )
                session.messages.append({"role": "assistant", "content": content})
                return content, None

            # Primero ejecutamos las lecturas. Si ademas hay escrituras en el
            # mismo turno, no las ejecutamos aun: le pedimos al modelo que las
            # reintente viendo ya los datos reales (evita enviar/crear con datos
            # incompletos).
            for name, args in reads:
                seen_reads.add((name, json.dumps(args, sort_keys=True)))
                result = self._execute(name, args)
                if name == "listar_eventos":
                    evs = (result.get("resultado") or {}).get("eventos")
                    if isinstance(evs, list):
                        session.ultimos_eventos = [
                            {
                                "id": e.get("id"),
                                "titulo": e.get("titulo"),
                                "inicio": e.get("inicio"),
                            }
                            for e in evs
                        ]
                session.messages.append(
                    {"role": "tool", "content": json.dumps(result, ensure_ascii=False)}
                )

            if writes:
                saw_write = True
                aviso = {
                    "ok": False,
                    "resultado": (
                        "Accion NO ejecutada todavia. Ya tienes los resultados de "
                        "lectura: vuelve a llamar la herramienta de escritura con la "
                        "informacion real."
                    ),
                }
                for _name, _args in writes:
                    session.messages.append(
                        {"role": "tool", "content": json.dumps(aviso, ensure_ascii=False)}
                    )

        return "No pude completar la solicitud (demasiados pasos).", None
