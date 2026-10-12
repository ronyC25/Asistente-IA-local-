"""Text-to-speech con Piper (con respaldo a la voz de Windows)."""
from __future__ import annotations

import io
import logging
import subprocess
import wave
from pathlib import Path

import numpy as np

from ..config import settings

log = logging.getLogger("asistente.voice.tts")

_voice = None


def _load():
    global _voice
    if _voice is not None:
        return _voice
    from piper import PiperVoice
    from piper.download_voices import download_voice

    name = settings.voice["tts_voice"]
    voices_dir = Path(settings.voice["voices_dir"])
    voices_dir.mkdir(parents=True, exist_ok=True)
    model_path = voices_dir / f"{name}.onnx"
    if not model_path.exists():
        log.info("descargando voz Piper '%s'...", name)
        download_voice(name, voices_dir)
    _voice = PiperVoice.load(str(model_path))
    return _voice


def sintetizar(texto: str) -> tuple[np.ndarray | None, int]:
    voice = _load()
    chunks = list(voice.synthesize(texto))
    if not chunks:
        return None, 0
    sample_rate = chunks[0].sample_rate
    audio = np.concatenate([c.audio_float_array for c in chunks]).astype("float32")
    return audio, sample_rate


def sintetizar_wav_bytes(texto: str) -> bytes | None:
    """Sintetiza el texto y devuelve un WAV (bytes) para enviar al navegador."""
    audio, sample_rate = sintetizar(texto)
    if audio is None or not len(audio):
        return None
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype("int16")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _hablar_sapi(texto: str) -> None:
    safe = texto.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{safe}')"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            timeout=120,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001
        print(f"[TTS] {texto}")


def hablar(texto: str) -> None:
    if not texto:
        return
    try:
        import sounddevice as sd

        audio, sample_rate = sintetizar(texto)
        if audio is not None and len(audio):
            sd.play(audio, sample_rate)
            sd.wait()
            return
    except Exception as exc:  # noqa: BLE001
        log.warning("Piper fallo (%s); uso la voz de Windows", exc)
    _hablar_sapi(texto)
