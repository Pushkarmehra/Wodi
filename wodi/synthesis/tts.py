"""
Piper TTS — Local streaming text-to-speech.

Streams synthesized audio chunks directly to sounddevice playback
for real-time output with no buffering delay.

Requires:
  - piper-tts installed: pip install piper-tts
  - Voice model downloaded: en_US-lessac-medium.onnx
    Download: https://huggingface.co/rhasspy/piper-voices

Also supports Kokoro TTS as an alternative backend.
"""
from __future__ import annotations

import asyncio
import io
import subprocess
import threading
from pathlib import Path
from typing import Any

from wodi.utils.logging import get_logger

log = get_logger(__name__)


class TTSEngine:
    """
    Text-to-Speech engine wrapper.

    Backends:
      - piper  : Fastest, runs locally via CLI or Python API
      - kokoro : More natural, Python library
      - disabled: Silent mode (useful for tests or accessibility)

    Usage:
        tts = TTSEngine(engine="piper", model_path="~/.wodi/models/tts/en_US-lessac-medium.onnx")
        tts.load()
        await tts.speak("Hello, I'm Wodi.")
    """

    def __init__(
        self,
        engine: str = "piper",
        model_path: str = "~/.wodi/models/tts/en_US-lessac-medium.onnx",
        config_path: str = "",
        rate: float = 1.0,
        volume: float = 0.85,
        stream: bool = True,
    ) -> None:
        self.engine = engine
        self._model_path = Path(model_path).expanduser()
        self._config_path = Path(config_path).expanduser() if config_path else None
        self._rate = rate
        self._volume = volume
        self._stream = stream
        self._piper_model: Any = None
        self._speaking = False
        self._stop_event = threading.Event()

    def load(self) -> None:
        """Load TTS model (call once at startup)."""
        if self.engine == "disabled":
            log.info("tts.disabled")
            return

        if self.engine == "piper":
            self._load_piper()
        elif self.engine == "kokoro":
            self._load_kokoro()

    def _load_piper(self) -> None:
        """Load Piper TTS model."""
        if not self._model_path.exists():
            log.warning(
                "tts.piper_model_missing",
                path=str(self._model_path),
                hint=(
                    "Download from: https://huggingface.co/rhasspy/piper-voices\n"
                    f"Expected path: {self._model_path}"
                ),
            )
            self.engine = "disabled"
            return
        try:
            from piper.voice import PiperVoice
            self._piper_model = PiperVoice.load(
                str(self._model_path),
                config_path=str(self._config_path) if self._config_path and self._config_path.exists() else None,
            )
            log.info("tts.piper_loaded", model=self._model_path.stem)
        except ImportError:
            log.warning("tts.piper_not_installed", fallback="cli_mode")
            self._piper_model = "cli"  # Use CLI mode
        except Exception as e:
            log.error("tts.piper_load_error", error=str(e))
            self.engine = "disabled"

    def _load_kokoro(self) -> None:
        try:
            import kokoro
            log.info("tts.kokoro_loaded")
        except ImportError:
            log.warning("tts.kokoro_missing", fallback="disabled")
            self.engine = "disabled"

    async def speak(self, text: str, on_chunk: Any | None = None) -> None:
        """
        Synthesize and play speech for the given text.
        If on_chunk is provided, calls it with each audio chunk (bytes).
        """
        if self.engine == "disabled" or not text.strip():
            return

        self._stop_event.clear()
        self._speaking = True

        try:
            if self.engine == "piper":
                await self._speak_piper(text, on_chunk)
            elif self.engine == "kokoro":
                await self._speak_kokoro(text, on_chunk)
        finally:
            self._speaking = False

    async def _speak_piper(self, text: str, on_chunk: Any | None) -> None:
        """Synthesize with Piper and stream to sounddevice."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._piper_speak_sync, text, on_chunk)

    def _piper_speak_sync(self, text: str, on_chunk: Any | None) -> None:
        try:
            import sounddevice as sd
            import numpy as np

            if self._piper_model and self._piper_model != "cli":
                # Python API mode
                audio_chunks = list(self._piper_model.synthesize_stream_raw(
                    text, sentence_silence=0.1
                ))
                for chunk in audio_chunks:
                    if self._stop_event.is_set():
                        break
                    audio = np.frombuffer(chunk, dtype=np.int16)
                    audio = (audio * self._volume).astype(np.int16)
                    if on_chunk:
                        on_chunk(chunk)
                    sd.play(audio, samplerate=22050, blocking=True)
            else:
                # CLI mode — pipe through piper executable
                self._piper_cli_speak(text, on_chunk)

        except Exception as e:
            log.error("tts.piper_speak_error", error=str(e))

    def _piper_cli_speak(self, text: str, on_chunk: Any | None) -> None:
        """Fallback: use piper CLI executable."""
        try:
            import sounddevice as sd
            import soundfile as sf
            import io

            proc = subprocess.run(
                ["piper", "--model", str(self._model_path), "--output_raw"],
                input=text.encode(),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout:
                import numpy as np
                audio = np.frombuffer(proc.stdout, dtype=np.int16)
                audio = (audio * self._volume).astype(np.int16)
                if on_chunk:
                    on_chunk(proc.stdout)
                sd.play(audio, samplerate=22050, blocking=True)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            log.warning("tts.piper_cli_error", error=str(e))

    async def _speak_kokoro(self, text: str, on_chunk: Any | None) -> None:
        """Synthesize with Kokoro."""
        try:
            import kokoro
            import sounddevice as sd
            import numpy as np

            loop = asyncio.get_event_loop()

            def _synth() -> None:
                samples = kokoro.generate(text, speed=self._rate)
                audio = (np.array(samples) * self._volume * 32767).astype(np.int16)
                sd.play(audio, samplerate=24000, blocking=True)

            await loop.run_in_executor(None, _synth)
        except Exception as e:
            log.error("tts.kokoro_speak_error", error=str(e))

    def stop(self) -> None:
        """Stop any currently playing speech."""
        self._stop_event.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        self._speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._speaking
