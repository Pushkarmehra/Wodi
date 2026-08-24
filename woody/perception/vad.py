"""
Silero VAD — Voice Activity Detection.

Wraps silero-vad to segment audio from a PyAudio microphone stream
into speech/silence events.

Events emitted:
  - on_speech_start()
  - on_speech_end(audio_bytes: bytes)   ← full utterance PCM, 16kHz mono 16-bit
"""
from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from woody.utils.logging import get_logger

log = get_logger(__name__)

SAMPLE_RATE = 16000        # Silero VAD requires 16kHz
CHUNK_SAMPLES = 512        # ~32ms per chunk at 16kHz (silero minimum)
BYTES_PER_SAMPLE = 2       # 16-bit PCM


class VADListener:
    """
    Background thread that reads microphone audio and emits voice activity events.

    Usage:
        def on_start(): print("speaking...")
        def on_end(audio): process_speech(audio)

        vad = VADListener(on_speech_start=on_start, on_speech_end=on_end)
        vad.start()
        # ... later ...
        vad.stop()
    """

    def __init__(
        self,
        threshold: float = 0.4,
        min_speech_ms: int = 250,
        max_silence_ms: int = 800,
        on_speech_start: Callable[[], None] | None = None,
        on_speech_end: Callable[[bytes], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.threshold = threshold
        self.min_speech_samples = int(SAMPLE_RATE * min_speech_ms / 1000)
        self.max_silence_samples = int(SAMPLE_RATE * max_silence_ms / 1000)
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._loop = loop

        self._running = False
        self._thread: threading.Thread | None = None
        self._vad_model: Any = None

    def start(self) -> None:
        """Start the VAD listener thread."""
        self._load_model()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="woody-vad")
        self._thread.start()
        log.info("vad.started", threshold=self.threshold)

    def stop(self) -> None:
        """Stop the VAD listener thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("vad.stopped")

    def _load_model(self) -> None:
        try:
            import torch
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
            )
            self._vad_model = model
            log.info("vad.model_loaded", backend="silero")
        except Exception as e:
            log.warning("vad.model_load_failed", error=str(e), fallback="energy_vad")
            self._vad_model = None

    def _run(self) -> None:
        """Main VAD loop — reads mic, detects speech, emits events."""
        try:
            import pyaudio
        except ImportError:
            log.error("vad.pyaudio_missing", hint="pip install pyaudio")
            return

        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=CHUNK_SAMPLES,
        )

        speech_buffer: list[bytes] = []
        silence_samples = 0
        speech_samples = 0
        in_speech = False

        log.info("vad.listening")
        try:
            while self._running:
                chunk = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                is_speech = self._is_speech(chunk)

                if is_speech:
                    silence_samples = 0
                    speech_samples += CHUNK_SAMPLES
                    speech_buffer.append(chunk)
                    if not in_speech and speech_samples >= self.min_speech_samples:
                        in_speech = True
                        self._emit_speech_start()
                else:
                    if in_speech:
                        silence_samples += CHUNK_SAMPLES
                        speech_buffer.append(chunk)  # keep trailing silence
                        if silence_samples >= self.max_silence_samples:
                            utterance = b"".join(speech_buffer)
                            self._emit_speech_end(utterance)
                            speech_buffer.clear()
                            silence_samples = 0
                            speech_samples = 0
                            in_speech = False
                    else:
                        speech_samples = max(0, speech_samples - CHUNK_SAMPLES // 2)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _is_speech(self, chunk: bytes) -> bool:
        """Run Silero VAD (or energy fallback) on a chunk."""
        try:
            if self._vad_model is not None:
                import torch
                audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                tensor = torch.from_numpy(audio)
                confidence = self._vad_model(tensor, SAMPLE_RATE).item()
                return confidence >= self.threshold
            else:
                # Energy-based fallback
                audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(audio**2))
                return rms > 500  # empirical threshold for 16-bit PCM
        except Exception:
            return False

    def _emit_speech_start(self) -> None:
        if self._on_speech_start:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._on_speech_start)
            else:
                self._on_speech_start()

    def _emit_speech_end(self, audio: bytes) -> None:
        if self._on_speech_end:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._on_speech_end, audio)
            else:
                self._on_speech_end(audio)
