"""API HTTP del asistente (FastAPI)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .avatar import handle_ws
from .config import ROOT, settings
from .factory import build_agent
from .scheduler import shutdown as stop_scheduler
from .scheduler import start as start_scheduler

_INDEX = ROOT / "web" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title=f"{settings.assistant_name} - Asistente IA local",
    lifespan=lifespan,
)

_agent = None
_sessions: dict[str, object] = {}


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    pending: dict | None = None


class TtsRequest(BaseModel):
    text: str


class SayRequest(BaseModel):
    texto: str


class TimerRequest(BaseModel):
    tipo: str = "temporizador"
    minutos: int | None = None
    etiqueta: str | None = None
    trabajo_min: int | None = None
    descanso_min: int | None = None
    descanso_largo_min: int | None = None
    ciclos: int | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": settings.model}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = _INDEX.read_text(encoding="utf-8")
    return HTMLResponse(html.replace("{{ASSISTANT_NAME}}", settings.assistant_name))


@app.get("/status")
def status() -> dict:
    from .tools import calendar, reminders, tasks

    return {
        "tareas_pendientes": tasks.listar_tareas(estado="pendientes")["total"],
        "recordatorios_pendientes": reminders.listar_recordatorios("pendientes")["total"],
        "eventos_proximos": calendar.listar_eventos()["total"],
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = get_agent()
    session = _sessions.get(req.session_id)
    if session is None:
        session = agent.new_session()
        _sessions[req.session_id] = session
    reply, pending = agent.handle(session, req.message)
    from .brain.emotions import limpiar_respuesta

    reply, _emociones = limpiar_respuesta(reply)
    return ChatResponse(reply=reply, pending=pending)


@app.post("/session/{session_id}/reset")
def reset(session_id: str) -> dict:
    _sessions.pop(session_id, None)
    return {"reset": session_id}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await handle_ws(ws)


@app.post("/tts")
def tts_endpoint(req: TtsRequest) -> Response:
    from .brain.emotions import limpiar_respuesta
    from .voice import tts as tts_mod

    texto, _emociones = limpiar_respuesta(req.text)
    wav = tts_mod.sintetizar_wav_bytes(texto)
    if not wav:
        return Response(status_code=400, content=b"")
    return Response(content=wav, media_type="audio/wav")


@app.get("/avatar/config")
def avatar_config() -> dict:
    """Configuracion del avatar para el frontend (modelos, escala, perfil lipsync)."""
    from pathlib import Path

    av = settings.avatar
    base = ROOT / "avatar"
    models = []
    for name, path in (av.get("models") or {}).items():
        try:
            rel = Path(path).resolve().relative_to(base).as_posix()
        except ValueError:
            rel = Path(path).name
        models.append({"name": name, "path": rel})
    return {
        "default": av.get("model"),
        "height": av.get("height", 350),
        "lipsync_profile": "public/lipsync/profile.json",
        "models": models,
    }


@app.post("/avatar/say")
def avatar_say(req: SayRequest) -> dict:
    """Hace hablar al avatar (usado por el scheduler de otros procesos)."""
    from .avatar import notificar_avatar

    return {"ok": notificar_avatar(req.texto)}


@app.get("/temporizadores")
def temporizadores() -> dict:
    """Temporizadores/pomodoros activos (o pausados) + config de pomodoro."""
    from .tools import timers

    res = timers.estado()
    return {"temporizadores": res["temporizadores"], "config": dict(settings.pomodoro)}


@app.post("/temporizadores")
def crear_temporizador(req: TimerRequest) -> dict:
    from .tools import timers

    try:
        return timers.iniciar(
            minutos=req.minutos,
            etiqueta=req.etiqueta,
            tipo=req.tipo,
            trabajo_min=req.trabajo_min,
            descanso_min=req.descanso_min,
            descanso_largo_min=req.descanso_largo_min,
            ciclos=req.ciclos,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/temporizadores/{tid}/{accion}")
def accion_temporizador(tid: int, accion: str) -> dict:
    from .tools import timers

    try:
        if accion == "pausar":
            return timers.pausar(id=tid)
        if accion == "reanudar":
            return timers.reanudar(id=tid)
        if accion in ("cancelar", "detener"):
            return timers.cancelar(id=tid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=f"accion no valida: {accion}")


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)


_AVATAR_DIR = ROOT / "avatar"
if _AVATAR_DIR.exists():
    app.mount("/avatar", StaticFiles(directory=str(_AVATAR_DIR), html=True), name="avatar")
