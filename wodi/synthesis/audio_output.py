"""
Audio Output — Low-latency audio routing for TTS playback.

Wraps sounddevice playback with:
  - Real-time RMS metering (feeds the orb animation)
  - Volume normalization and soft-clipping
  - Interruption support (stop current speech immediately)
  - Device selection (default output / specific device)
"""
from __future__ import annotations

import io
import threading
import time
from typing import Any, Callable

import numpy as np

from wodi.utils.logging import get_logger

log = get_logger(__name__)


class AudioOutput:
    """
    Manages audio output for TTS and sound feedback.

    Provides real-time RMS metering so the orb can animate
    in sync with the spoken audio.

    Usage:
        audio = AudioOutput(device=None, sample_rate=22050)
        audio.start()
        audio.play_pcm(pcm_bytes, on_rms=orb.set_rms)
        audio.stop()
    """

    def __init__(
        self,
        device: str | int | None = None,
        sample_rate: int = 22050,
        volume: float = 0.85,
        latency: str = "low",
    ) -> None:
        self._device = device
        self._sample_rate = sample_rate
        self._volume = volume
        self._latency = latency
        self._playing = False
        self._stop_event = threading.Event()
        self._stream: Any | None = None
        self._available = self._check_sounddevice()

    def _check_sounddevice(self) -> bool:
        try:
            import sounddevice  # noqa: F401
            return True
        except ImportError:
            log.warning("audio.sounddevice_missing", hint="pip install sounddevice")
            return False

    def play_pcm(
        self,
        pcm_bytes: bytes,
        dtype: str = "int16",
        channels: int = 1,
        on_rms: Callable[[float], None] | None = None,
    ) -> None:
        """
        Play raw PCM bytes through the default audio output.
        Calls on_rms(0.0-1.0) in real-time for orb animation.
        Blocks until playback completes or stop() is called.
        """
        if not self._available or not pcm_bytes:
            return

        self._stop_event.clear()
        self._playing = True

        try:
            import sounddevice as sd

            audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            audio = np.clip(audio * self._volume, -1.0, 1.0)

            chunk_size = int(self._sample_rate * 0.05)  # 50ms chunks
            pos = 0

            while pos < len(audio) and not self._stop_event.is_set():
                chunk = audio[pos: pos + chunk_size]
                sd.play(chunk, samplerate=self._sample_rate, device=self._device, blocking=False)
                sd.wait()

                if on_rms:
                    rms = float(np.sqrt(np.mean(chunk ** 2)))
                    on_rms(min(1.0, rms * 8))  # Scale to 0-1 range

                pos += chunk_size

        except Exception as e:
            log.error("audio.play_error", error=str(e))
        finally:
            self._playing = False

    def play_wav(self, wav_bytes: bytes, on_rms: Callable[[float], None] | None = None) -> None:
        """Play a WAV file from bytes."""
        if not self._available:
            return
        try:
            import soundfile as sf
            buf = io.BytesIO(wav_bytes)
            data, sr = sf.read(buf, dtype="float32")
            data = np.clip(data * self._volume, -1.0, 1.0)

            import sounddevice as sd
            sd.play(data, samplerate=sr, device=self._device, blocking=True)
            if on_rms:
                rms = float(np.sqrt(np.mean(data ** 2)))
                on_rms(min(1.0, rms * 8))
        except Exception as e:
            log.error("audio.play_wav_error", error=str(e))

    def beep(self, frequency: float = 440.0, duration: float = 0.15, volume: float = 0.3) -> None:
        """Play a short feedback beep (wake word confirmation, error, etc.)."""
        if not self._available:
            return
        try:
            import sounddevice as sd
            t = np.linspace(0, duration, int(self._sample_rate * duration), endpoint=False)
            # Sine wave with fast attack/release envelope
            envelope = np.minimum(t / 0.01, 1.0) * np.minimum((duration - t) / 0.03, 1.0)
            tone = (np.sin(2 * np.pi * frequency * t) * envelope * volume).astype(np.float32)
            sd.play(tone, samplerate=self._sample_rate, blocking=True)
        except Exception as e:
            log.debug("audio.beep_error", error=str(e))

    def stop(self) -> None:
        """Stop current playback immediately."""
        self._stop_event.set()
        if self._available:
            try:
                import sounddevice as sd
                sd.stop()
            except Exception:
                pass
        self._playing = False

    def list_devices(self) -> list[dict]:
        """Return available audio output devices."""
        if not self._available:
            return []
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            return [
                {"index": i, "name": d["name"], "channels": d["max_output_channels"]}
                for i, d in enumerate(devices)
                if d["max_output_channels"] > 0
            ]
        except Exception:
            return []

    @property
    def is_playing(self) -> bool:
        return self._playing
