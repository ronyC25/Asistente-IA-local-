"""Loop principal del agente (tool-calling + confirmacion)."""
from __future__ import annotations

import json
from typing import Any

import ollama

from .confirm import (
    build_proposal,
    classify_confirmation,
    dominio_lectura,
    looks_like_action,
    looks_like_query,
    periodo_de_texto,
    quiere_historial_recordatorios,
)
from .registry import Registry


class Session:
    def __init__(self, system_prompt: str) -> None:
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self.pending: list[tuple[str, dict]] | None = None


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
_TOOLS_CON_PERIODO = ("listar_eventos", "listar_tareas", "listar_recordatorios")

# Dominio de datos -> herramienta de lectura por defecto (fallback determinista).
_DOMINIO_TOOL = {
    "tareas": "listar_tareas",
    "recordatorios": "listar_recordatorios",
    "notas": "consultar_notas",
    "listas": "consultar_listas",
    "eventos": "listar_eventos",
    "email": "leer_email",
}


def _args_dominio(dominio: str, user_text: str | None) -> dict:
    """Argumentos por defecto para la lectura forzada de un dominio."""
    t = (user_text or "").lower()
    if dominio == "tareas":
        if any(w in t for w in ("todas", "todos", "base de datos", "completad")):
            return {"estado": "todas"}
        return {}
    if dominio == "recordatorios":
        est = "historial" if quiere_historial_recordatorios(user_text or "") else "pendientes"
        return {"estado": est}
    if dominio in ("notas", "listas"):
        return {"accion": "listar"}
    return {}


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

    def _ajustar_args(
        self, parsed: list[tuple[str, dict]], user_text: str | None
    ) -> list[tuple[str, dict]]:
        """Ajustes deterministas de argumentos, para no depender del modelo:

        - historial de recordatorios (estado por defecto -> 'historial');
        - rangos de fecha relativos (fija 'periodo' y descarta desde/hasta).
        """
        if not user_text:
            return parsed
        periodo = periodo_de_texto(user_text)
        ajustado: list[tuple[str, dict]] = []
        for name, args in parsed:
            args = dict(args or {})
            if name == "listar_recordatorios":
                est = str(args.get("estado", "")).strip().lower()
                if est in ("", "pendiente", "pendientes", "todos", "todas") and (
                    quiere_historial_recordatorios(user_text)
                ):
                    args["estado"] = "historial"
            if periodo and name in _TOOLS_CON_PERIODO:
                p, n = periodo
                args["periodo"] = p
                if n is not None:
                    args["dias"] = n
                args.pop("desde", None)
                args.pop("hasta", None)
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

        self._trim(session)
        session.messages.append({"role": "user", "content": user_text})
        return self._run_loop(session, user_text=user_text)

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
    ) -> tuple[str, dict | None]:
        saw_write = False
        saw_tool = False
        seen_reads: set = set()
        for _ in range(self.max_iters):
            response = self._call(session, think=think)
            message = response.get("message", {}) or {}
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                content = message.get("content") or ""
                nudge: str | None = None
                if user_text and stage < 2:
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
                session.messages.append({"role": "assistant", "content": content})
                return content, None

            saw_tool = True
            parsed: list[tuple[str, dict]] = [
                (tc["function"]["name"], _norm_args(tc["function"].get("arguments")))
                for tc in tool_calls
            ]
            parsed = self._ajustar_args(parsed, user_text)
            assistant_msg = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
            session.messages.append(assistant_msg)

            reads, writes = partition_calls(parsed, self.registry)

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
                content = (resp.get("message") or {}).get("content") or ""
                session.messages.append({"role": "assistant", "content": content})
                return content, None

            # Primero ejecutamos las lecturas. Si ademas hay escrituras en el
            # mismo turno, no las ejecutamos aun: le pedimos al modelo que las
            # reintente viendo ya los datos reales (evita enviar/crear con datos
            # incompletos).
            for name, args in reads:
                seen_reads.add((name, json.dumps(args, sort_keys=True)))
                result = self._execute(name, args)
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
