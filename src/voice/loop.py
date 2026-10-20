"""Orquestador del modo voz: wake word -> STT -> agente -> TTS."""
from __future__ import annotations

import logging

import numpy as np

from ..config import settings
from ..brain.voice_guard import parece_eco
from . import stt, tts
from .wake import WakeWord

log = logging.getLogger("asistente.voice")

_SALIR = {"salir", "adios", "adiós", "apagate", "apágate", "hasta luego", "chau"}
_CHUNK = 1280  # 80 ms a 16 kHz, tamano esperado por openWakeWord


def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(frame.astype("float32")))))


def _beep(sample_rate: int, freq: float = 880.0, ms: int = 120) -> None:
    try:
        import sounddevice as sd

        t = np.linspace(0, ms / 1000, int(sample_rate * ms / 1000), endpoint=False)
        tone = 0.3 * np.sin(2 * np.pi * freq * t).astype("float32")
        sd.play(tone, sample_rate)
        sd.wait()
    except Exception:  # noqa: BLE001
        pass


def _record_until_silence(stream, sample_rate: int, chunk: int) -> np.ndarray:
    """Graba desde el microfono hasta detectar silencio sostenido."""
    cfg = settings.voice
    threshold = 0.02
    silence_limit = int(cfg["silence_ms"] / 1000 * sample_rate / chunk) + 1
    max_frames = int(cfg["max_record_seconds"] * sample_rate / chunk)
    frames: list[np.ndarray] = []
    silence = 0
    started = False

    while len(frames) < max_frames:
        data, _overflow = stream.read(chunk)
        frame = data[:, 0].copy()
        frames.append(frame)
        if _rms(frame) > threshold:
            started = True
            silence = 0
        elif started:
            silence += 1
            if silence >= silence_limit:
                break

    audio = np.concatenate(frames).astype("float32") / 32768.0
    return audio


def run(agent, debug: bool = False) -> None:
    import sounddevice as sd

    sample_rate = settings.voice["sample_rate"]
    device = settings.voice.get("input_device")
    nombre = settings.assistant_name

    try:
        info = sd.query_devices(device, "input")
        devname = info["name"]
    except Exception as exc:  # noqa: BLE001
        devname = f"(desconocido: {exc})"

    print(f"=== {nombre} - modo voz (modelo: {settings.model}) ===")
    print(f"Microfono: {devname}")
    print("Cargando componentes de voz...")
    ww = WakeWord()
    session = agent.new_session()
    ultima: str | None = None

    print(f"Di '{ww.name.replace('_', ' ')}' para activarme. Di 'salir' para terminar.")
    if debug:
        print("[debug] mostrando la puntuacion del wake word en tiempo real\n")
    else:
        print()

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=_CHUNK,
            device=device,
        ) as stream:
            running_max = 0.0
            bloques = 0
            while True:
                data, _overflow = stream.read(_CHUNK)
                frame = data[:, 0]
                score = ww.score(frame)

                if debug:
                    running_max = max(running_max, score)
                    bloques += 1
                    if bloques >= 12:  # ~1 s
                        print(
                            f"\r[debug] wake score max ultimo segundo: {running_max:.3f} "
                            f"(umbral {ww.threshold:.2f})    ",
                            end="",
                            flush=True,
                        )
                        running_max = 0.0
                        bloques = 0

                if score < ww.threshold:
                    continue

                ww.reset()
                _beep(sample_rate)
                if debug:
                    print()
                print("[te escucho...]")
                audio = _record_until_silence(stream, sample_rate, _CHUNK)
                texto = stt.transcribir(audio, sample_rate=sample_rate)
                if not texto:
                    print("[no entendi nada]")
                    continue
                if ultima and parece_eco(texto, ultima):
                    print("[ignorado: posible eco del asistente]")
                    continue

                print(f"Tu > {texto}")
                if texto.lower().strip(" .!?") in _SALIR:
                    tts.hablar("Hasta luego.")
                    break

                respuesta, _pending = agent.handle(session, texto)
                ultima = respuesta
                print(f"{nombre} > {respuesta}\n")
                tts.hablar(respuesta)
    except KeyboardInterrupt:
        print("\nCerrando modo voz.")
