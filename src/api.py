"""API HTTP del asistente (FastAPI)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .config import settings
from .factory import build_agent
from .scheduler import shutdown as stop_scheduler
from .scheduler import start as start_scheduler


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": settings.model}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = get_agent()
    session = _sessions.get(req.session_id)
    if session is None:
        session = agent.new_session()
        _sessions[req.session_id] = session
    reply, pending = agent.handle(session, req.message)
    return ChatResponse(reply=reply, pending=pending)


@app.post("/session/{session_id}/reset")
def reset(session_id: str) -> dict:
    _sessions.pop(session_id, None)
    return {"reset": session_id}


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
