"""
Wake Word Detection for Wodi.

Listens continuously for the configured wake phrase using OpenWakeWord,
with Porcupine as a fallback engine. Fires a callback when the wake word
is detected, which gates the VAD + STT pipeline.

Engines:
  - openwakeword: Free, runs on CPU. Uses stock models (alexa, hey_jarvis, etc.)
                  Custom model support via .tflite path in config.
  - porcupine:    Picovoice Porcupine — very low false-accept rate, requires key.
  - disabled:     Wake word detection off; rely on hotkey only.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from wodi.utils.logging import get_logger

log = get_logger(__name__)

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80ms at 16kHz — OpenWakeWord recommended


class WakeWordDetector:
    """
    Continuously listens on the microphone for the configured wake phrase.

    Usage:
        def on_wake():
            print("Wake word detected!")

        detector = WakeWordDetector(
            engine="openwakeword",
            phrase="hey jarvis",
            threshold=0.5,
            on_wake=on_wake,
        )
        detector.start()
        # ... later ...
        detector.stop()
    """

    def __init__(
        self,
        engine: str = "openwakeword",
        phrase: str = "hey jarvis",
        threshold: float = 0.5,
        on_wake: Callable[[], None] | None = None,
        porcupine_key: str = "",
        custom_model_path: str | None = None,
    ) -> None:
        self.engine = engine
        self.phrase = phrase
        self.threshold = threshold
        self._on_wake = on_wake
        self._porcupine_key = porcupine_key
        self._custom_model_path = custom_model_path

        self._running = False
        self._thread: threading.Thread | None = None
        self._model: Any = None
        self._active = False  # Whether wake word is actively gating

    def start(self) -> None:
        if self.engine == "disabled":
            log.info("wake_word.disabled")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="wodi-wakeword"
        )
        self._thread.start()
        log.info("wake_word.started", engine=self.engine, phrase=self.phrase)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("wake_word.stopped")

    def _run(self) -> None:
        if self.engine == "porcupine":
            self._run_porcupine()
        else:
            self._run_openwakeword()

    # ── OpenWakeWord ──────────────────────────────────────────────────────────

    def _run_openwakeword(self) -> None:
        try:
            import pyaudio
            from openwakeword.model import Model
        except ImportError as e:
            log.error("wake_word.import_error", engine="openwakeword", error=str(e))
            return

        # Map phrase to available OWW model names
        model_name = self._resolve_oww_model()

        try:
            if self._custom_model_path:
                oww = Model(wakeword_models=[self._custom_model_path], inference_framework="onnx")
            else:
                oww = Model(wakeword_models=[model_name], inference_framework="onnx")
        except Exception as e:
            log.error("wake_word.model_load_failed", model=model_name, error=str(e))
            return

        log.info("wake_word.model_ready", model=model_name)

        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=CHUNK_SAMPLES,
        )

        try:
            while self._running:
                chunk = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                import numpy as np
                audio = np.frombuffer(chunk, dtype=np.int16)
                prediction = oww.predict(audio)
                for model_key, score in prediction.items():
                    if score >= self.threshold:
                        log.info("wake_word.detected", model=model_key, score=f"{score:.3f}")
                        oww.reset()  # Reset internal state after trigger
                        self._fire_callback()
                        break
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _resolve_oww_model(self) -> str:
        """Map a natural phrase to the closest OpenWakeWord stock model name."""
        phrase_lower = self.phrase.lower().replace(" ", "_")
        oww_models = {
            "hey_jarvis": "hey_jarvis",
            "alexa": "alexa",
            "hey_mycroft": "hey_mycroft",
            "hey_rhasspy": "hey_rhasspy",
        }
        if phrase_lower in oww_models:
            return oww_models[phrase_lower]
        # Default fallback
        log.warning(
            "wake_word.phrase_not_found",
            phrase=self.phrase,
            fallback="hey_jarvis",
            hint="Use custom_model_path in config for a custom-trained model.",
        )
        return "hey_jarvis"

    # ── Porcupine ─────────────────────────────────────────────────────────────

    def _run_porcupine(self) -> None:
        try:
            import pvporcupine
            import pyaudio
        except ImportError as e:
            log.error("wake_word.import_error", engine="porcupine", error=str(e))
            return

        if not self._porcupine_key:
            log.error("wake_word.porcupine_no_key")
            return

        try:
            porcupine = pvporcupine.create(
                access_key=self._porcupine_key,
                keywords=["jarvis"],  # stock keyword; replace with custom .ppn
            )
        except Exception as e:
            log.error("wake_word.porcupine_init_failed", error=str(e))
            return

        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length,
        )

        log.info("wake_word.model_ready", engine="porcupine")
        try:
            while self._running:
                chunk = stream.read(porcupine.frame_length, exception_on_overflow=False)
                import struct
                pcm = struct.unpack_from("h" * porcupine.frame_length, chunk)
                result = porcupine.process(pcm)
                if result >= 0:
                    log.info("wake_word.detected", engine="porcupine", keyword_index=result)
                    self._fire_callback()
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            porcupine.delete()

    def _fire_callback(self) -> None:
        if self._on_wake:
            try:
                self._on_wake()
            except Exception as e:
                log.error("wake_word.callback_error", error=str(e))
