"""
Wake Word Detection for Woody.

Listens continuously for the configured wake phrase.

Engines:
  - openwakeword: Uses OpenWakeWord for stock models (alexa, hey_mycroft, hey_rhasspy, etc.)
                  or custom .onnx/.tflite models. Automatically falls back to the Whisper
                  keyword spotter for custom phrases like "hey woody".
  - whisper:      Fast, accurate speech-based keyword spotting using Faster-Whisper + VAD.
                  Reliably detects "Hey Woody", "Hi Woody", "Hello Woody", "Woody", etc.
  - porcupine:    Picovoice Porcupine — very low false-accept rate, requires key.
  - disabled:     Wake word detection off; rely on hotkey only.
"""
from __future__ import annotations

import collections
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from woody.utils.logging import get_logger

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
            phrase="hey woody",
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
        phrase: str = "hey woody",
        threshold: float = 0.5,
        on_wake: Callable[[], None] | None = None,
        porcupine_key: str = "",
        custom_model_path: str | None = None,
    ) -> None:
        self.engine = engine.lower().strip()
        self.phrase = phrase.lower().strip()
        self.threshold = threshold
        self._on_wake = on_wake
        self._porcupine_key = porcupine_key
        self._custom_model_path = custom_model_path

        self._running = False
        self._thread: threading.Thread | None = None
        self._model: Any = None
        self._last_wake_time: float = 0.0
        self._wake_cooldown: float = 1.5  # seconds between wake triggers

        # Build regex for matching "hey woody", "hi woody", "woody", "hello woody", etc.
        self._build_phrase_pattern()

    def _build_phrase_pattern(self) -> None:
        """Compile regex pattern for detecting the wake phrase."""
        if "woody" in self.phrase or "wodi" in self.phrase:
            # Allow common phonetic/ASR variations of "woody"
            self._phrase_re = re.compile(
                r"\b(hey|hi|hello|ok|okay)?\s*(woody|woodi|wodi|woodie|hoodie|would he|wordy)\b",
                re.IGNORECASE,
            )
        else:
            # Generic phrase pattern
            escaped = re.escape(self.phrase)
            self._phrase_re = re.compile(rf"\b{escaped}\b", re.IGNORECASE)

    def start(self) -> None:
        if self.engine == "disabled":
            log.info("wake_word.disabled")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="woody-wakeword"
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
        elif self.engine == "openwakeword" and self._has_stock_oww_model():
            self._run_openwakeword()
        else:
            # Use fast Whisper keyword spotting for "hey woody" or custom phrases
            self._run_whisper_spotter()

    def _has_stock_oww_model(self) -> bool:
        """Check if OpenWakeWord has an exact pre-trained stock model for this phrase."""
        if self._custom_model_path:
            return True
        phrase_key = self.phrase.replace(" ", "_")
        stock_models = {"alexa", "hey_mycroft", "hey_rhasspy", "hey_jarvis"}
        return phrase_key in stock_models

    # ── Whisper Keyword Spotter ───────────────────────────────────────────────

    def _run_whisper_spotter(self) -> None:
        """
        Fast, streaming keyword spotter for 'Hey Woody' and custom phrases.
        Monitors microphone audio with energy VAD and transcribes speech segments
        using Faster-Whisper.
        """
        try:
            import pyaudio
            import numpy as np
            from faster_whisper import WhisperModel
        except ImportError as e:
            log.error("wake_word.import_error", engine="whisper_spotter", error=str(e))
            return

        try:
            # Use base model (cached locally, fast on CPU)
            stt_model = WhisperModel("base", device="cpu", compute_type="int8")
            log.info("wake_word.whisper_spotter_ready", phrase=self.phrase)
        except Exception as e:
            log.error("wake_word.whisper_load_failed", error=str(e))
            return

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                rate=SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=CHUNK_SAMPLES,
            )
        except Exception as e:
            log.error("wake_word.audio_stream_failed", error=str(e))
            pa.terminate()
            return

        # Ring buffer for audio: keep up to 2.5 seconds of audio
        buffer_chunks = int(2.5 * SAMPLE_RATE / CHUNK_SAMPLES)
        audio_ring = collections.deque(maxlen=buffer_chunks)
        speech_detected = False
        silence_count = 0
        speech_chunks = 0
        min_speech_chunks = 3   # ~240ms minimum speech
        max_speech_chunks = 25  # ~2.0s maximum speech window
        energy_threshold = 280  # RMS amplitude threshold for speech detection

        try:
            while self._running:
                chunk = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                audio_ring.append(chunk)

                # Compute RMS energy
                pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(pcm ** 2)) if len(pcm) > 0 else 0.0

                if rms > energy_threshold:
                    if not speech_detected:
                        speech_detected = True
                        speech_chunks = 0
                    speech_chunks += 1
                    silence_count = 0
                else:
                    if speech_detected:
                        silence_count += 1
                        speech_chunks += 1

                # Check if speech segment is complete (short pause or max speech length reached)
                if speech_detected and (silence_count >= 4 or speech_chunks >= max_speech_chunks):
                    if speech_chunks >= min_speech_chunks:
                        # Assemble the recent audio buffer
                        raw_audio = b"".join(list(audio_ring))
                        audio_np = (
                            np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
                            / 32768.0
                        )

                        now = time.time()
                        if now - self._last_wake_time > self._wake_cooldown:
                            try:
                                segments, _ = stt_model.transcribe(
                                    audio_np,
                                    language="en",
                                    beam_size=1,
                                    vad_filter=True,
                                )
                                text = " ".join(s.text for s in segments).strip()
                                if text:
                                    log.debug("wake_word.spotter_heard", text=text)
                                    if self._phrase_re.search(text):
                                        log.info("wake_word.detected", phrase=self.phrase, text=text)
                                        self._last_wake_time = now
                                        self._fire_callback()
                                        audio_ring.clear()
                            except Exception as e:
                                log.debug("wake_word.spotter_transcribe_error", error=str(e))

                    # Reset speech detection state
                    speech_detected = False
                    speech_chunks = 0
                    silence_count = 0
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    # ── OpenWakeWord ──────────────────────────────────────────────────────────

    def _run_openwakeword(self) -> None:
        try:
            import pyaudio
            import numpy as np
            from openwakeword.model import Model
        except ImportError as e:
            log.error("wake_word.import_error", engine="openwakeword", error=str(e))
            return

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
        try:
            stream = pa.open(
                rate=SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=CHUNK_SAMPLES,
            )
        except Exception as e:
            log.error("wake_word.audio_stream_failed", error=str(e))
            pa.terminate()
            return

        try:
            while self._running:
                chunk = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                audio = np.frombuffer(chunk, dtype=np.int16)
                prediction = oww.predict(audio)
                for model_key, score in prediction.items():
                    if score >= self.threshold:
                        now = time.time()
                        if now - self._last_wake_time > self._wake_cooldown:
                            log.info("wake_word.detected", model=model_key, score=f"{score:.3f}")
                            self._last_wake_time = now
                            oww.reset()
                            self._fire_callback()
                        break
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _resolve_oww_model(self) -> str:
        """Map phrase to available OpenWakeWord stock model name."""
        phrase_lower = self.phrase.lower().replace(" ", "_")
        oww_models = {
            "alexa": "alexa",
            "hey_mycroft": "hey_mycroft",
            "hey_rhasspy": "hey_rhasspy",
            "hey_jarvis": "hey_jarvis",
        }
        return oww_models.get(phrase_lower, "hey_jarvis")

    # ── Porcupine ─────────────────────────────────────────────────────────────

    def _run_porcupine(self) -> None:
        try:
            import pvporcupine
            import pyaudio
            import struct
        except ImportError as e:
            log.error("wake_word.import_error", engine="porcupine", error=str(e))
            return

        if not self._porcupine_key:
            log.error("wake_word.porcupine_no_key")
            return

        try:
            porcupine = pvporcupine.create(
                access_key=self._porcupine_key,
                keywords=["jarvis"],
            )
        except Exception as e:
            log.error("wake_word.porcupine_init_failed", error=str(e))
            return

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                rate=porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=porcupine.frame_length,
            )
        except Exception as e:
            log.error("wake_word.audio_stream_failed", error=str(e))
            pa.terminate()
            porcupine.delete()
            return

        log.info("wake_word.model_ready", engine="porcupine")
        try:
            while self._running:
                chunk = stream.read(porcupine.frame_length, exception_on_overflow=False)
                pcm = struct.unpack_from("h" * porcupine.frame_length, chunk)
                result = porcupine.process(pcm)
                if result >= 0:
                    now = time.time()
                    if now - self._last_wake_time > self._wake_cooldown:
                        log.info("wake_word.detected", engine="porcupine", keyword_index=result)
                        self._last_wake_time = now
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

