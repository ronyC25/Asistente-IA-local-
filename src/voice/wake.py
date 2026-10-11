"""Deteccion de la palabra clave (wake word) con openWakeWord."""
from __future__ import annotations

import logging

import numpy as np

from ..config import settings

log = logging.getLogger("asistente.voice.wake")


class WakeWord:
    def __init__(self) -> None:
        from openwakeword.model import Model

        self.name = settings.voice["wake_model"]
        self.threshold = settings.voice["wake_threshold"]
        log.info("cargando wake word '%s' (umbral %.2f)", self.name, self.threshold)
        self.model = Model(
            wakeword_models=[self.name], inference_framework="onnx"
        )

    def reset(self) -> None:
        try:
            self.model.reset()
        except Exception:  # noqa: BLE001
            pass

    def score(self, frame: np.ndarray) -> float:
        """Devuelve la puntuacion maxima para el frame int16 (1280 muestras)."""
        preds = self.model.predict(frame)
        if not preds:
            return 0.0
        return float(max(preds.values()))

    def detectado(self, frame: np.ndarray) -> bool:
        return self.score(frame) >= self.threshold
