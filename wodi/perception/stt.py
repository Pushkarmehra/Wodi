"""
Streaming STT using Faster-Whisper.

Accepts audio bytes from VAD, returns:
  - Partial transcription events (for caption streaming)
  - Final transcription with word timestamps

Domain adaptation: accepts an `initial_prompt` derived from screen OCR
so that app names, code identifiers, and jargon transcribe correctly.
"""
from __future__ import annotations

import asyncio
import io
import queue
import threading
from collections.abc import Callable
from typing import Any

import numpy as np

from wodi.utils.logging import get_logger

log = get_logger(__name__)

SAMPLE_RATE = 16000


class STTEngine:
    """
    Faster-Whisper streaming speech-to-text.

    Usage:
        stt = STTEngine(model="base", device="auto")
        stt.load()
        result = stt.transcribe(audio_bytes, initial_prompt="VS Code Python")
        print(result.text)
    """

    def __init__(
        self,
        model: str = "base",
        device: str = "auto",
        language: str = "en",
        beam_size: int = 5,
        on_partial: Callable[[str], None] | None = None,
    ) -> None:
        self.model_name = model
        self.device = device
        self.language = language
        self.beam_size = beam_size
        self._on_partial = on_partial
        self._model: Any = None
        self._lock = threading.Lock()

    def load(self) -> None:
        """Load the Faster-Whisper model (call once at startup)."""
        try:
            from faster_whisper import WhisperModel

            device = self._resolve_device()
            compute_type = "float16" if device == "cuda" else "int8"

            log.info("stt.loading", model=self.model_name, device=device, compute_type=compute_type)
            self._model = WhisperModel(
                self.model_name,
                device=device,
                compute_type=compute_type,
            )
            log.info("stt.model_ready", model=self.model_name)
        except ImportError:
            log.error("stt.import_error", hint="pip install faster-whisper")
        except Exception as e:
            log.error("stt.load_failed", error=str(e))

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def transcribe(
        self,
        audio_bytes: bytes,
        initial_prompt: str | None = None,
    ) -> "TranscriptionResult":
        """
        Transcribe a complete audio utterance (bytes, 16kHz mono 16-bit PCM).
        Returns a TranscriptionResult with text and word-level segments.
        """
        if self._model is None:
            log.warning("stt.not_loaded", hint="Call stt.load() first")
            return TranscriptionResult(text="", segments=[])

        # Convert raw bytes → float32 numpy array
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        with self._lock:
            try:
                segments_gen, info = self._model.transcribe(
                    audio,
                    language=self.language,
                    beam_size=self.beam_size,
                    initial_prompt=initial_prompt,
                    word_timestamps=True,
                    vad_filter=True,  # Whisper's built-in VAD filter
                )
                segments = list(segments_gen)
                full_text = " ".join(s.text.strip() for s in segments)
                log.info("stt.transcribed", text=full_text[:80], lang=info.language)
                return TranscriptionResult(
                    text=full_text.strip(),
                    segments=[
                        {"start": s.start, "end": s.end, "text": s.text.strip()}
                        for s in segments
                    ],
                    language=info.language,
                    language_probability=info.language_probability,
                )
            except Exception as e:
                log.error("stt.transcribe_error", error=str(e))
                return TranscriptionResult(text="", segments=[])

    async def transcribe_async(
        self,
        audio_bytes: bytes,
        initial_prompt: str | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> "TranscriptionResult":
        """Async wrapper — runs transcription in a thread pool."""
        lp = loop or asyncio.get_event_loop()
        return await lp.run_in_executor(
            None, self.transcribe, audio_bytes, initial_prompt
        )

    def unload(self) -> None:
        """Release the model from memory."""
        self._model = None
        log.info("stt.unloaded")


class TranscriptionResult:
    def __init__(
        self,
        text: str,
        segments: list[dict],
        language: str = "en",
        language_probability: float = 1.0,
    ) -> None:
        self.text = text
        self.segments = segments
        self.language = language
        self.language_probability = language_probability

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def __repr__(self) -> str:
        return f"TranscriptionResult(text={self.text!r}, lang={self.language})"
