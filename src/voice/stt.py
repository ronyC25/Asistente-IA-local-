"""Speech-to-text con faster-whisper."""
from __future__ import annotations

import logging

import numpy as np

from ..config import settings

log = logging.getLogger("asistente.voice.stt")

_model = None
_device_usado: str | None = None

_CUDA_HINTS = ("cublas", "cudnn", "cuda", "gpu")


def _candidates(force_cpu: bool = False) -> list[tuple[str, str]]:
    if force_cpu:
        return [("cpu", "int8")]
    cfg = settings.voice
    device = cfg["whisper_device"]
    compute = cfg["whisper_compute"]
    if device == "auto":
        return [("cpu", "int8"), ("cuda", "float16")]
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return [(device, compute)]


def _load(force_cpu: bool = False):
    global _model, _device_usado
    if _model is not None and not force_cpu:
        return _model
    from faster_whisper import WhisperModel

    model_name = settings.voice["whisper_model"]
    last: Exception | None = None
    for device, compute in _candidates(force_cpu):
        try:
            log.info("cargando Whisper '%s' en %s (%s)", model_name, device, compute)
            _model = WhisperModel(model_name, device=device, compute_type=compute)
            _device_usado = device
            return _model
        except Exception as exc:  # noqa: BLE001
            last = exc
            log.warning("Whisper no cargo en %s: %s", device, exc)
    raise RuntimeError(f"no se pudo cargar Whisper: {last}")


def _run(audio: np.ndarray, language: str | None) -> str:
    model = _load()
    lang = language or settings.language
    segments, _info = model.transcribe(
        np.asarray(audio, dtype="float32"),
        language=lang,
        beam_size=1,
        vad_filter=True,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def transcribir(
    audio: np.ndarray, sample_rate: int = 16000, language: str | None = None
) -> str:
    global _model
    try:
        return _run(audio, language)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if _device_usado != "cpu" and any(k in msg for k in _CUDA_HINTS):
            log.warning("GPU no disponible (%s); cambio a CPU", exc)
            _model = None
            _load(force_cpu=True)
            return _run(audio, language)
        raise
