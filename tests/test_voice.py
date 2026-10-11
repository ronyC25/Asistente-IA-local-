from __future__ import annotations

import numpy as np
import pytest

from src.config import settings
from src.voice import loop


class FakeStream:
    def __init__(self, frames):
        self._frames = list(frames)
        self._i = 0

    def read(self, n):
        if self._i < len(self._frames):
            frame = self._frames[self._i]
            self._i += 1
        else:
            frame = np.zeros(n, dtype="int16")
        return frame.reshape(-1, 1), False


def test_voice_config_presente():
    for clave in (
        "whisper_model",
        "tts_voice",
        "wake_model",
        "wake_threshold",
        "sample_rate",
        "silence_ms",
        "max_record_seconds",
    ):
        assert clave in settings.voice


def test_rms():
    assert loop._rms(np.zeros(100, dtype="int16")) == 0.0
    assert loop._rms(np.full(100, 1000, dtype="int16")) == pytest.approx(1000.0, rel=0.01)


def test_record_para_tras_silencio():
    frames = [np.full(1280, 3000, dtype="int16")] * 5 + [
        np.zeros(1280, dtype="int16")
    ] * 60
    audio = loop._record_until_silence(FakeStream(frames), 16000, 1280)
    # 5 frames con voz + 12 de silencio (900 ms / 80 ms + 1)
    assert len(audio) == 17 * 1280
    assert audio.dtype == np.float32
    assert audio.max() <= 1.0


def test_record_sin_voz_respeta_maximo():
    audio = loop._record_until_silence(FakeStream([]), 16000, 1280)
    max_frames = int(settings.voice["max_record_seconds"] * 16000 / 1280)
    assert len(audio) == max_frames * 1280


def test_modulos_importan():
    import src.voice.stt  # noqa: F401
    import src.voice.tts  # noqa: F401
    import src.voice.wake  # noqa: F401
