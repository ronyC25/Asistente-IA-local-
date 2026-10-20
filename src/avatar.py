"""Backend del avatar Live2D: WebSocket que une microfono, wake word, STT,
agente y TTS (Piper), y emite estados/expresiones/audio al frontend."""
from __future__ import annotations

import asyncio
import json
import logging
import time

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from .brain.emotions import limpiar_respuesta
from .brain.voice_guard import parece_eco
from .config import settings
from .factory import build_agent
from .voice import stt, tts
from .voice.wake import WakeWord

log = logging.getLogger("asistente.avatar")

CHUNK = 1280  # 80 ms @ 16 kHz (tamano que espera openWakeWord)
SAMPLE_RATE = 16000
_UMBRAL_VOZ = 0.02
_SALIR = {"salir", "adios", "adiós", "apagate", "apágate", "hasta luego", "chau"}

_wake: WakeWord | None = None
_agent = None

# Clientes de avatar conectados (para avisarles desde el scheduler: voz + lip-sync).
_CLIENTES: set = set()
_LOOP = None

# Ultima frase reproducida (texto, momento) para el filtro anti-eco global.
_ULTIMA_VOZ: tuple[str, float] | None = None


def _marcar_voz(texto: str) -> None:
    global _ULTIMA_VOZ
    _ULTIMA_VOZ = (texto or "", time.monotonic())


def _es_eco(texto: str, ultima: str | None) -> bool:
    if ultima and parece_eco(texto, ultima):
        return True
    if _ULTIMA_VOZ and (time.monotonic() - _ULTIMA_VOZ[1]) < 20:
        return parece_eco(texto, _ULTIMA_VOZ[0])
    return False


def notificar_avatar(texto: str, wav: bytes | None = None) -> bool:
    """Hace hablar a los avatares conectados. True si habia alguno.

    ``wav`` (opcional): audio ya sintetizado (aviso inmediato, sin TTS).
    Pensado para llamarse desde otro hilo (p. ej. el scheduler).
    """
    if not texto or not _CLIENTES or _LOOP is None or _LOOP.is_closed():
        return False
    try:
        asyncio.run_coroutine_threadsafe(_hablar_en_avatares(texto, wav), _LOOP)
        return True
    except Exception:  # noqa: BLE001
        log.exception("no se pudo avisar al avatar")
        return False


async def _hablar_en_avatares(texto: str, wav: bytes | None = None) -> None:
    _marcar_voz(texto)
    # Primero el texto (asi el avatar lo muestra aunque falle el TTS)...
    for ws in list(_CLIENTES):
        try:
            await ws.send_json({"type": "reply", "text": texto})
        except Exception:  # noqa: BLE001
            _CLIENTES.discard(ws)
    # ...y despues la voz (pre-sintetizada o al vuelo).
    if wav is None:
        try:
            wav = await asyncio.to_thread(tts.sintetizar_wav_bytes, texto)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo sintetizar la voz del aviso")
            return
    if not wav:
        return
    for ws in list(_CLIENTES):
        try:
            await ws.send_bytes(wav)
        except Exception:  # noqa: BLE001
            _CLIENTES.discard(ws)


def _get_wake() -> WakeWord:
    global _wake
    if _wake is None:
        _wake = WakeWord()
    return _wake


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(frame.astype("float32")))))


async def handle_ws(ws: WebSocket) -> None:
    global _LOOP
    await ws.accept()
    _LOOP = asyncio.get_running_loop()
    _CLIENTES.add(ws)
    try:
        wake = await asyncio.to_thread(_get_wake)
    except Exception as exc:  # noqa: BLE001
        _CLIENTES.discard(ws)
        await ws.send_json({"type": "error", "message": f"wake word: {exc}"})
        await ws.close()
        return

    agent = _get_agent()
    session = agent.new_session()
    await ws.send_json({"type": "ready", "wake": wake.name, "model": settings.avatar["model"]})
    await ws.send_json({"type": "state", "value": "idle"})

    leftover = np.zeros(0, dtype="int16")
    rec: dict | None = None
    busy = False
    ultima_respuesta: str | None = None

    async def process_text(texto: str) -> None:
        nonlocal busy, ultima_respuesta
        busy = True
        try:
            await ws.send_json({"type": "state", "value": "thinking"})
            reply, pending = await asyncio.to_thread(agent.handle, session, texto)
            limpio, emociones = limpiar_respuesta(reply)
            ultima_respuesta = limpio
            _marcar_voz(limpio)
            if emociones:
                await ws.send_json({"type": "expression", "value": emociones[-1]})
            await ws.send_json({"type": "reply", "text": limpio})
            if pending:
                await ws.send_json({"type": "pending", "active": True})
                await ws.send_json({"type": "state", "value": "idle"})
                return
            await ws.send_json({"type": "pending", "active": False})
            await ws.send_json({"type": "state", "value": "speaking"})
            wav = await asyncio.to_thread(tts.sintetizar_wav_bytes, limpio)
            if wav:
                await ws.send_bytes(wav)
            await ws.send_json({"type": "state", "value": "idle"})
        finally:
            busy = False

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if msg.get("bytes"):
                if busy:
                    continue  # half-duplex: ignora el mic mientras piensa/habla
                leftover = np.concatenate(
                    [leftover, np.frombuffer(msg["bytes"], dtype="int16")]
                )
                while len(leftover) >= CHUNK:
                    frame = leftover[:CHUNK].copy()
                    leftover = leftover[CHUNK:]

                    if rec is None:
                        if wake.detectado(frame):
                            wake.reset()
                            # Barge-in: si el avatar estaba hablando, que se calle.
                            await ws.send_json({"type": "stop_speaking"})
                            rec = {
                                "frames": [],
                                "silence": 0,
                                "started": False,
                                "limit": int(
                                    settings.voice["silence_ms"] / 1000 * SAMPLE_RATE / CHUNK
                                )
                                + 1,
                                "max": int(
                                    settings.voice["max_record_seconds"] * SAMPLE_RATE / CHUNK
                                ),
                            }
                            await ws.send_json({"type": "state", "value": "listening"})
                        continue

                    rec["frames"].append(frame)
                    if _rms(frame) > _UMBRAL_VOZ:
                        rec["started"] = True
                        rec["silence"] = 0
                    elif rec["started"]:
                        rec["silence"] += 1
                    if rec["started"] and (
                        rec["silence"] >= rec["limit"] or len(rec["frames"]) >= rec["max"]
                    ):
                        audio = np.concatenate(rec["frames"]).astype("float32") / 32768.0
                        rec = None
                        texto = await asyncio.to_thread(
                            stt.transcribir, audio, SAMPLE_RATE
                        )
                        if not texto:
                            await ws.send_json({"type": "state", "value": "idle"})
                            continue
                        if _es_eco(texto, ultima_respuesta):
                            log.info("ignoro posible eco del avatar: %r", texto)
                            await ws.send_json({"type": "state", "value": "idle"})
                            continue
                        await ws.send_json({"type": "you", "text": texto})
                        if texto.lower().strip(" .!?") in _SALIR:
                            await ws.send_json({"type": "reply", "text": "Hasta luego."})
                            await ws.close()
                            return
                        await process_text(texto)

            elif msg.get("text"):
                try:
                    payload = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                tipo = payload.get("type")
                if tipo == "text":
                    texto = (payload.get("text") or "").strip()
                    if texto and not busy:
                        await ws.send_json({"type": "you", "text": texto})
                        await process_text(texto)
                elif tipo == "mic":
                    if not payload.get("enabled"):
                        rec = None
                elif tipo == "barge_in":
                    rec = None

    except WebSocketDisconnect:
        log.info("cliente de avatar desconectado")
    except Exception:  # noqa: BLE001
        log.exception("error en el websocket del avatar")
    finally:
        _CLIENTES.discard(ws)
