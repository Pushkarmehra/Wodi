"""
Piper TTS — Local text-to-speech with multiple backend strategies.

Backends (in priority order):
  1. piper Python API  — PiperVoice.synthesize() → raw int16 chunks
  2. piper CLI         — pipe text through the piper executable
  3. pyttsx3           — cross-platform fallback, no model needed
  4. disabled          — silent mode (tests / accessibility)

Requires:
  - piper-tts installed: pip install piper-tts
  - Voice model downloaded: en_US-lessac-medium.onnx
    Download: https://huggingface.co/rhasspy/piper-voices
    Place at:  ~/.wodi/models/tts/en_US-lessac-medium.onnx

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
    Text-to-Speech engine wrapper supporting Piper, Kokoro, pyttsx3, and silent mode.

    Usage::

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
        self._piper_sample_rate: int = 22050
        self._speaking = False
        self._stop_event = threading.Event()

    # ── Loading ──────────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load the TTS model (call once at startup)."""
        if self.engine == "disabled":
            log.info("tts.disabled")
            return

        if self.engine == "piper":
            self._load_piper()
        elif self.engine == "kokoro":
            self._load_kokoro()
        # pyttsx3 is loaded on-demand (no model file needed)

    def _load_piper(self) -> None:
        """Load Piper TTS model, falling back gracefully on any failure."""
        if not self._model_path.exists():
            log.warning(
                "tts.piper_model_missing",
                path=str(self._model_path),
                hint=(
                    "Download from: https://huggingface.co/rhasspy/piper-voices\n"
                    f"Expected path: {self._model_path}\n"
                    "Falling back to pyttsx3 TTS."
                ),
            )
            self.engine = "pyttsx3"
            return

        try:
            from piper.voice import PiperVoice

            config_arg = (
                str(self._config_path)
                if self._config_path and self._config_path.exists()
                else None
            )
            self._piper_model = PiperVoice.load(
                str(self._model_path), config_path=config_arg
            )
            # Grab the actual sample rate from the loaded model config
            if hasattr(self._piper_model, "config") and hasattr(
                self._piper_model.config, "sample_rate"
            ):
                self._piper_sample_rate = self._piper_model.config.sample_rate
            log.info(
                "tts.piper_loaded",
                model=self._model_path.stem,
                sample_rate=self._piper_sample_rate,
            )
        except ImportError:
            log.warning("tts.piper_not_installed", fallback="cli_then_pyttsx3")
            self._piper_model = "cli"
        except Exception as e:
            log.error("tts.piper_load_error", error=str(e), fallback="pyttsx3")
            self.engine = "pyttsx3"

    def _load_kokoro(self) -> None:
        try:
            import kokoro  # noqa: F401

            log.info("tts.kokoro_loaded")
        except ImportError:
            log.warning("tts.kokoro_missing", fallback="pyttsx3")
            self.engine = "pyttsx3"

    # ── Public API ───────────────────────────────────────────────────────────────

    async def speak(self, text: str, on_chunk: Any | None = None) -> None:
        """
        Synthesize and play speech for the given text.

        Args:
            text: The text to speak.
            on_chunk: Optional callback(bytes) called with each audio chunk.
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
            elif self.engine == "pyttsx3":
                await self._speak_pyttsx3(text)
        except Exception as e:
            log.error("tts.speak_error", engine=self.engine, error=str(e))
        finally:
            self._speaking = False

    # ── Piper backend ────────────────────────────────────────────────────────────

    async def _speak_piper(self, text: str, on_chunk: Any | None) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._piper_speak_sync, text, on_chunk)

    def _piper_speak_sync(self, text: str, on_chunk: Any | None) -> None:
        if self._piper_model and self._piper_model != "cli":
            self._piper_api_speak(text, on_chunk)
        else:
            self._piper_cli_speak(text, on_chunk)

    def _piper_api_speak(self, text: str, on_chunk: Any | None) -> None:
        """
        Use the PiperVoice Python API to synthesize speech.

        The piper-tts API changed over versions:
          - Old: synthesize_stream_raw(text) → iterator[bytes]
          - New: synthesize(text, wav_file)  → writes WAV to a file-like object
                 synthesize_ids_to_raw(phoneme_ids, ...) → iterator[bytes]

        We probe for whichever method exists and use a WAV buffer as fallback.
        """
        try:
            import numpy as np
            import sounddevice as sd

            # ── Strategy 1: synthesize_stream_raw (old piper-tts ≤ 1.x) ──
            if hasattr(self._piper_model, "synthesize_stream_raw"):
                chunks = list(
                    self._piper_model.synthesize_stream_raw(
                        text, sentence_silence=0.1
                    )
                )
                for chunk in chunks:
                    if self._stop_event.is_set():
                        break
                    if on_chunk:
                        on_chunk(chunk)
                    audio = np.frombuffer(chunk, dtype=np.int16)
                    audio = (audio * self._volume).astype(np.int16)
                    sd.play(audio, samplerate=self._piper_sample_rate, blocking=True)
                return

            # ── Strategy 2: synthesize(text, wav_file) (piper-tts ≥ 2.x) ──
            if hasattr(self._piper_model, "synthesize"):
                buf = io.BytesIO()
                import wave

                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(self._piper_sample_rate)
                    self._piper_model.synthesize(text, wf)

                # Read back using stdlib wave + numpy — no soundfile dependency
                buf.seek(0)
                with wave.open(buf, "rb") as wf:
                    raw = wf.readframes(wf.getnframes())
                    sr = wf.getframerate()

                data = np.frombuffer(raw, dtype=np.int16)
                if self._stop_event.is_set():
                    return
                audio = (data * self._volume).astype(np.int16)
                if on_chunk:
                    on_chunk(audio.tobytes())
                sd.play(audio, samplerate=sr, blocking=True)
                return

            # ── Strategy 3: unknown API — fall back to CLI ──
            log.warning("tts.piper_api_unknown", hint="Falling back to piper CLI")
            self._piper_cli_speak(text, on_chunk)

        except Exception as e:
            log.error("tts.piper_api_error", error=str(e), fallback="cli")
            self._piper_cli_speak(text, on_chunk)

    def _piper_cli_speak(self, text: str, on_chunk: Any | None) -> None:
        """Fallback: pipe text through the piper CLI executable."""
        try:
            import numpy as np
            import sounddevice as sd

            proc = subprocess.run(
                ["piper", "--model", str(self._model_path), "--output_raw"],
                input=text.encode(),
                capture_output=True,
                timeout=60,
            )
            if proc.returncode == 0 and proc.stdout:
                audio = np.frombuffer(proc.stdout, dtype=np.int16)
                audio = (audio * self._volume).astype(np.int16)
                if on_chunk:
                    on_chunk(proc.stdout)
                sd.play(audio, samplerate=self._piper_sample_rate, blocking=True)
            else:
                raise RuntimeError(
                    f"piper CLI exited {proc.returncode}: {proc.stderr.decode()[:200]}"
                )
        except FileNotFoundError:
            log.warning("tts.piper_cli_not_found", fallback="pyttsx3")
            self._speak_pyttsx3_sync(text)
        except subprocess.TimeoutExpired:
            log.warning("tts.piper_cli_timeout")
        except Exception as e:
            log.error("tts.piper_cli_error", error=str(e))

    # ── Kokoro backend ───────────────────────────────────────────────────────────

    async def _speak_kokoro(self, text: str, on_chunk: Any | None) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._kokoro_speak_sync, text, on_chunk)

    def _kokoro_speak_sync(self, text: str, on_chunk: Any | None) -> None:
        try:
            import kokoro
            import numpy as np
            import sounddevice as sd

            samples = kokoro.generate(text, speed=self._rate)
            audio = (np.array(samples) * self._volume * 32767).astype(np.int16)
            if on_chunk:
                on_chunk(audio.tobytes())
            sd.play(audio, samplerate=24000, blocking=True)
        except Exception as e:
            log.error("tts.kokoro_speak_error", error=str(e))

    # ── pyttsx3 fallback backend ─────────────────────────────────────────────────

    async def _speak_pyttsx3(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._speak_pyttsx3_sync, text)

    def _speak_pyttsx3_sync(self, text: str) -> None:
        """Use pyttsx3 as a last-resort TTS fallback (no model file needed)."""
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", int(engine.getProperty("rate") * self._rate))
            engine.setProperty("volume", self._volume)
            engine.say(text)
            engine.runAndWait()
        except ImportError:
            log.warning(
                "tts.pyttsx3_not_installed",
                hint="pip install pyttsx3  — or install a Piper voice model for better quality",
            )
        except Exception as e:
            log.error("tts.pyttsx3_error", error=str(e))

    # ── Control ──────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Stop any currently playing speech immediately."""
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
