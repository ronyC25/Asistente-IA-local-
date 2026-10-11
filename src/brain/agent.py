"""Loop principal del agente (tool-calling + confirmacion)."""
from __future__ import annotations

import json
from typing import Any

import ollama

from .confirm import build_proposal, classify_confirmation, looks_like_action
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
        num_ctx: int = 8192,
        host: str | None = None,
    ) -> None:
        self.registry = registry
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_iters = max_iters
        self.num_ctx = num_ctx
        self.client = ollama.Client(host=host) if host else ollama.Client()

    def new_session(self) -> Session:
        return Session(self.system_prompt)

    def _call(self, session: Session) -> dict:
        return self.client.chat(
            model=self.model,
            messages=session.messages,
            tools=self.registry.schemas(),
            options={"temperature": self.temperature, "num_ctx": self.num_ctx},
        )

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

    def _run_loop(
        self, session: Session, user_text: str | None = None, allow_nudge: bool = True
    ) -> tuple[str, dict | None]:
        saw_write = False
        for _ in range(self.max_iters):
            response = self._call(session)
            message = response.get("message", {}) or {}
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                content = message.get("content") or ""
                if (
                    allow_nudge
                    and user_text
                    and not saw_write
                    and looks_like_action(user_text)
                ):
                    session.messages.append({"role": "system", "content": self._NUDGE})
                    return self._run_loop(session, user_text=user_text, allow_nudge=False)
                session.messages.append({"role": "assistant", "content": content})
                return content, None

            parsed: list[tuple[str, dict]] = [
                (tc["function"]["name"], _norm_args(tc["function"].get("arguments")))
                for tc in tool_calls
            ]
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

            # Primero ejecutamos las lecturas. Si ademas hay escrituras en el
            # mismo turno, no las ejecutamos aun: le pedimos al modelo que las
            # reintente viendo ya los datos reales (evita enviar/crear con datos
            # incompletos).
            for name, args in reads:
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
