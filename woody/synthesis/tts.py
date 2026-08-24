"""
Text-to-Speech Engine for Woody.

Backends:
  1. inworld   — Inworld AI TTS-2 Neural Voices (Avery, ultra-natural conversational AI)
  2. edge-tts  — Microsoft Edge Neural AI Voices (expressive fallback)
  3. SAPI5     — Native Windows Speech (zero-latency offline fallback)
  4. pyttsx3   — Cross-platform TTS fallback
  5. piper     — Local ONNX Piper TTS
  6. disabled  — Silent mode
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from woody.utils.logging import get_logger

log = get_logger(__name__)


class TTSEngine:
    """
    Text-to-Speech engine wrapper supporting Inworld AI TTS-2, Edge Neural TTS, Piper, SAPI, and pyttsx3.

    Usage::

        tts = TTSEngine(engine="inworld", voice="Avery")
        tts.load()
        await tts.speak("Hello! I am Woody.")
    """

    def __init__(
        self,
        engine: str = "inworld",
        model_path: str = "~/.woody/models/tts/en_US-lessac-medium.onnx",
        config_path: str = "",
        voice: str = "Avery",
        pet_voice: str = "community-blcuaurhzmvi",
        rate: float = 1.0,
        volume: float = 0.90,
        stream: bool = True,
        inworld_api_key: str = "",
        inworld_model: str = "inworld-tts-2",
        delivery_mode: str = "CREATIVE",
        language: str = "AUTO",
    ) -> None:
        self.engine = engine.lower().strip()
        self._model_path = Path(model_path).expanduser()
        self._config_path = Path(config_path).expanduser() if config_path else None
        self._default_voice = voice
        self._pet_voice = pet_voice or os.getenv("INWORLD_PET_VOICE", "community-blcuaurhzmvi")
        self._voice = voice
        self._mode = "normal"
        self._rate = rate
        self._volume = volume
        self._stream = stream
        self._inworld_api_key = (
            inworld_api_key or os.getenv("INWORLD_API_KEY", "")
        ).strip()
        self._inworld_model = inworld_model or os.getenv("INWORLD_MODEL", "inworld-tts-2")
        self._delivery_mode = delivery_mode or os.getenv("INWORLD_DELIVERY_MODE", "CREATIVE")
        self._language = language or os.getenv("INWORLD_LANGUAGE", "AUTO")
        self._http_client: Any | None = None
        self._piper_model: Any = None
        self._piper_sample_rate: int = 22050
        self._speaking = False
        self._stop_event = threading.Event()
        self._audio_cache: dict[str, bytes] = {}
        self._cache_dir = Path("~/.woody/cache/tts").expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ── Loading ──────────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load or initialize the TTS engine."""
        if self.engine == "disabled":
            log.info("tts.disabled")
            return

        if self.engine in ("inworld", "auto"):
            if self._inworld_api_key:
                self.engine = "inworld"
                try:
                    import httpx
                    self._http_client = httpx.AsyncClient(
                        timeout=20.0,
                        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
                    )
                except Exception:
                    pass

                log.info(
                    "tts.inworld_ready",
                    voice=self._voice,
                    model=self._inworld_model,
                    delivery_mode=self._delivery_mode,
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._prewarm_common_cache())
                except RuntimeError:
                    pass
                return
            else:
                log.warning(
                    "tts.inworld_key_missing",
                    hint="Set INWORLD_API_KEY in .env for ultra-realistic neural voice",
                    fallback="edge-tts",
                )
                self.engine = "edge-tts"



        if self.engine == "edge-tts":
            try:
                import edge_tts  # noqa: F401
                log.info("tts.edge_neural_ready", voice=self._voice)
                return
            except ImportError:
                log.warning("tts.edge_tts_not_found", fallback="piper_or_sapi")


        if self.engine == "piper":
            if self._model_path.exists():
                self._load_piper()
            else:
                try:
                    import edge_tts  # noqa: F401
                    self.engine = "edge-tts"
                    log.info("tts.auto_selected_edge_tts", voice=self._voice)
                except ImportError:
                    self.engine = "pyttsx3"
                    log.info("tts.auto_selected_sapi")
        elif self.engine == "kokoro":
            self._load_kokoro()

    def _load_piper(self) -> None:
        """Load Piper TTS model."""
        if not self._model_path.exists():
            self.engine = "edge-tts"
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
            if hasattr(self._piper_model, "config") and hasattr(
                self._piper_model.config, "sample_rate"
            ):
                self._piper_sample_rate = self._piper_model.config.sample_rate
            log.info(
                "tts.piper_loaded",
                model=self._model_path.stem,
                sample_rate=self._piper_sample_rate,
            )
        except Exception as e:
            log.warning("tts.piper_load_fallback", error=str(e))
            self.engine = "edge-tts"

    def _load_kokoro(self) -> None:
        try:
            import kokoro  # noqa: F401
            log.info("tts.kokoro_loaded")
        except ImportError:
            self.engine = "edge-tts"

    # ── Public API ───────────────────────────────────────────────────────────────

    # ── Public API ───────────────────────────────────────────────────────────────

    async def speak(self, text: str, on_chunk: Any | None = None) -> None:
        """
        Synthesize and play speech for the given text with sentence-level pipelining.
        """
        if self.engine == "disabled" or not text.strip():
            return

        clean_full = self._clean_for_speech(text)
        if not clean_full or clean_full == ".":
            return

        # Split into sentences for pipelined instant playback
        sentences = self._split_into_sentences(clean_full)
        if len(sentences) > 1:
            q: asyncio.Queue[str | None] = asyncio.Queue()
            for s in sentences:
                await q.put(s)
            await q.put(None)
            await self.speak_sentence_stream(q, on_chunk)
            return

        self._stop_event.clear()
        self._speaking = True

        try:
            if self.engine == "inworld":
                await self._speak_inworld(clean_full, on_chunk)
            elif self.engine == "edge-tts":
                await self._speak_edge_tts(clean_full)
            elif self.engine == "piper":
                await self._speak_piper(clean_full, on_chunk)
            elif self.engine == "kokoro":
                await self._speak_kokoro(clean_full, on_chunk)
            else:
                await self._speak_pyttsx3(clean_full)
        except Exception as e:
            log.error("tts.speak_error", engine=self.engine, error=str(e))
            try:
                await self._speak_pyttsx3(clean_full)
            except Exception:
                pass
        finally:
            self._speaking = False

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentence/clause chunks on natural pause boundaries for immediate voice output."""
        clause_regex = re.compile(r'([.!?\n]+|[,;:—]\s+)')
        parts = []
        buf = text
        while buf:
            m = clause_regex.search(buf)
            if not m:
                if buf.strip():
                    parts.append(buf.strip())
                break
            prefix = buf[:m.end()].strip()
            buf = buf[m.end():]
            words = prefix.split()
            if len(words) >= 2 or any(p in prefix for p in '.!?\n'):
                parts.append(prefix)
            elif parts:
                parts[-1] = parts[-1] + " " + prefix
            else:
                parts.append(prefix)
        return parts if parts else [text.strip()]

    async def speak_sentence_stream(
        self,
        sentence_queue: asyncio.Queue[str | None],
        on_chunk: Any | None = None,
    ) -> None:
        """
        Pipelined sentence synthesis & playback worker:
        Synthesizes sentence N+1 in background while sentence N is actively playing.
        Produces instant voice response matching on-screen text generation speed.
        """
        if self.engine == "disabled":
            return

        self._stop_event.clear()
        self._speaking = True

        synth_queue: asyncio.Queue[tuple[bytes | None, str] | None] = asyncio.Queue()

        async def _synthesizer():
            try:
                while not self._stop_event.is_set():
                    try:
                        sentence = await asyncio.wait_for(sentence_queue.get(), timeout=0.15)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

                    if sentence is None or self._stop_event.is_set():
                        await synth_queue.put(None)
                        break

                    clean_sent = self._clean_for_speech(sentence)
                    if not clean_sent or clean_sent == ".":
                        continue

                    if self.engine == "inworld":
                        audio_bytes = await self._synthesize_inworld_chunk(clean_sent)
                    else:
                        audio_bytes = None

                    await synth_queue.put((audio_bytes, clean_sent))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.debug("tts.stream_synth_error", error=str(e))
            finally:
                try:
                    await synth_queue.put(None)
                except Exception:
                    pass

        async def _player():
            loop = asyncio.get_running_loop()
            try:
                while not self._stop_event.is_set():
                    try:
                        item = await asyncio.wait_for(synth_queue.get(), timeout=0.15)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

                    if item is None or self._stop_event.is_set():
                        break

                    audio_bytes, sent_text = item
                    if audio_bytes:
                        if on_chunk:
                            on_chunk(audio_bytes)
                        temp_path = None
                        try:
                            import tempfile
                            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                                f.write(audio_bytes)
                                temp_path = f.name

                            played = await loop.run_in_executor(None, self._play_mp3_native, temp_path)
                            if not played and not self._stop_event.is_set():
                                await self._speak_pyttsx3(sent_text)
                        finally:
                            if temp_path and os.path.exists(temp_path):
                                try:
                                    os.remove(temp_path)
                                except Exception:
                                    pass
                    elif not self._stop_event.is_set():
                        # Fallback speak for this sentence
                        if self.engine == "edge-tts":
                            await self._speak_edge_tts(sent_text)
                        elif self.engine == "piper":
                            await self._speak_piper(sent_text, on_chunk)
                        elif self.engine == "kokoro":
                            await self._speak_kokoro(sent_text, on_chunk)
                        else:
                            await self._speak_pyttsx3(sent_text)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.debug("tts.stream_player_error", error=str(e))

        try:
            await asyncio.gather(_synthesizer(), _player())
        except asyncio.CancelledError:
            pass
        finally:
            self._speaking = False


    # ── Inworld AI TTS Backend (Avery / inworld-tts-2) ───────────────────────────

    async def _prewarm_common_cache(self) -> None:
        """Pre-fetch and cache common assistant openers in background for 0ms instant speech."""
        common = [
            "I am Woody. What do you seek?",
            "Consider it done.",
            "Summoned. What is your will?",
            "As you command.",
            "The shadows obey.",
            "I am watching."
        ]
        for phrase in common:
            try:
                await self._synthesize_inworld_chunk(phrase)
            except Exception:
                pass


    async def _synthesize_inworld_chunk(self, clean_text: str) -> bytes | None:
        """Synthesize a single sentence chunk over persistent HTTP connection with caching."""

        if not self._inworld_api_key or not clean_text:
            return None

        import base64
        import hashlib
        import httpx

        # 1. Check in-memory cache
        cache_key = f"{self._voice}_{self._inworld_model}_{self._rate}_{clean_text}"
        if cache_key in self._audio_cache:
            return self._audio_cache[cache_key]

        # 2. Check disk cache
        key_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
        disk_file = self._cache_dir / f"{key_hash}.mp3"
        if disk_file.exists():
            try:
                cached_bytes = disk_file.read_bytes()
                if cached_bytes:
                    self._audio_cache[cache_key] = cached_bytes
                    return cached_bytes
            except Exception:
                pass

        voice = self._voice or "Avery"
        model = self._inworld_model or "inworld-tts-2"
        headers = {
            "Authorization": f"Basic {self._inworld_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": clean_text,
            "voiceId": voice,
            "modelId": model,
            "audioConfig": {
                "speakingRate": self._rate,
            },
            "deliveryMode": self._delivery_mode or "CREATIVE",
            "language": self._language or "AUTO",
        }

        try:
            client = self._http_client
            if client is None:
                client = httpx.AsyncClient(
                    timeout=15.0,
                    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
                )
                self._http_client = client

            resp = await client.post("https://api.inworld.ai/tts/v1/voice", json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                b64 = data.get("audioContent")
                if b64:
                    raw_audio = base64.b64decode(b64)
                    self._audio_cache[cache_key] = raw_audio
                    try:
                        disk_file.write_bytes(raw_audio)
                    except Exception:
                        pass
                    return raw_audio
        except Exception as e:
            log.debug("tts.inworld_chunk_err", error=str(e))
        return None


    async def _speak_inworld(self, text: str, on_chunk: Any | None = None) -> None:
        """
        Synthesize and play speech using Inworld AI TTS-2 API with expressive delivery.
        Supports HTTP Streaming (:stream NDJSON) and batch non-streaming endpoint with instant barge-in.
        """
        import base64
        import json
        import tempfile
        import httpx

        clean_text = self._clean_for_speech(text)
        if not clean_text or clean_text == ".":
            return

        if not self._inworld_api_key:
            log.warning("tts.inworld_no_key", fallback="edge-tts")
            await self._speak_edge_tts(text)
            return

        voice = self._voice or "Avery"
        model = self._inworld_model or "inworld-tts-2"
        headers = {
            "Authorization": f"Basic {self._inworld_api_key}",
            "Content-Type": "application/json",
        }

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name

            client = self._http_client
            if client is None:
                client = httpx.AsyncClient(
                    timeout=20.0,
                    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
                )
                self._http_client = client

            if self._stream:
                url = "https://api.inworld.ai/tts/v1/voice:stream"
                payload = {
                    "text": clean_text,
                    "voice_id": voice,
                    "model_id": model,
                    "audio_config": {
                        "audio_encoding": "MP3",
                        "speaking_rate": self._rate,
                    },
                    "delivery_mode": self._delivery_mode or "CREATIVE",
                    "language": self._language or "AUTO",
                }

                chunks_received = 0
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        err_body = (await resp.aread()).decode("utf-8", errors="ignore")
                        raise RuntimeError(f"Inworld TTS HTTP {resp.status_code}: {err_body}")

                    with open(temp_path, "wb") as mp3_out:
                        async for line in resp.aiter_lines():
                            if self._stop_event.is_set():
                                return
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                audio_b64 = data.get("result", {}).get("audioContent")
                                if audio_b64:
                                    raw_chunk = base64.b64decode(audio_b64)
                                    mp3_out.write(raw_chunk)
                                    chunks_received += 1
                                    if on_chunk:
                                        on_chunk(raw_chunk)
                            except Exception as parse_err:
                                log.debug("tts.inworld_stream_parse_err", error=str(parse_err))

            else:
                url = "https://api.inworld.ai/tts/v1/voice"
                payload = {
                    "text": clean_text,
                    "voiceId": voice,
                    "modelId": model,
                    "timestampType": "WORD",
                    "audioConfig": {
                        "speakingRate": self._rate,
                    },
                    "deliveryMode": self._delivery_mode or "CREATIVE",
                    "language": self._language or "AUTO",
                }

                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(f"Inworld TTS HTTP {resp.status_code}: {resp.text}")
                data = resp.json()
                audio_b64 = data.get("audioContent")
                if not audio_b64:
                    raise RuntimeError("Inworld TTS returned empty audioContent")
                audio_bytes = base64.b64decode(audio_b64)
                with open(temp_path, "wb") as mp3_out:
                    mp3_out.write(audio_bytes)
                if on_chunk:
                    on_chunk(audio_bytes)

            if self._stop_event.is_set() or not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                return

            # Play audio using native Windows MCI playback with instant interruption
            loop = asyncio.get_running_loop()
            played = await loop.run_in_executor(None, self._play_mp3_native, temp_path)
            if not played and not self._stop_event.is_set():
                await self._speak_pyttsx3(text)

        except Exception as e:
            log.warning("tts.inworld_error", error=str(e), fallback="edge-tts")
            # Fall back smoothly to edge-tts -> pyttsx3
            try:
                await self._speak_edge_tts(text)
            except Exception:
                await self._speak_pyttsx3(text)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass


    # ── Edge Neural TTS Backend (Natural Accents) ────────────────────────────────

    def _clean_for_speech(self, text: str) -> str:
        """Clean and format text for natural, conversational Siri-like speech."""
        # 1. Remove markdown code blocks and inline code
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]*`', '', text)
        # 2. Strip HTML/XML tags
        text = re.sub(r'<[^>]+>', '', text)
        # 3. Replace URLs with simple spoken reference
        text = re.sub(r'https?://[^\s)]+', 'the web link', text)
        # 4. Strip markdown symbols (*, _, #, >, ~, [, ], etc.)
        text = re.sub(r'[*_#~>\[\]\(\)]', '', text)
        # 5. Clean bullet points, emojis, and excessive dashes
        text = re.sub(r'^\s*[-•*]\s+', '', text, flags=re.MULTILINE)
        # 6. Normalize whitespace and clean punctuation pauses
        text = re.sub(r'\s+', ' ', text).strip()
        # 7. Ensure clean ending for natural falling intonation
        if text and not text[-1] in '.!?':
            text += '.'
        return text

    async def _speak_edge_tts(self, text: str) -> None:
        """Synthesize and play speech using Microsoft Edge Neural Voices with Siri cadence."""
        import tempfile
        import edge_tts

        clean_text = self._clean_for_speech(text)
        if not clean_text or clean_text == '.':
            return

        voice = self._voice or "en-US-AriaNeural"
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name

            rate_pct = f"{int((self._rate - 1.0) * 100):+d}%" if self._rate != 1.0 else "+1%"
            volume_pct = f"{int((self._volume - 1.0) * 100):+d}%" if self._volume != 1.0 else "+0%"
            pitch_str = "+1Hz"

            communicate = edge_tts.Communicate(
                clean_text,
                voice,
                rate=rate_pct,
                volume=volume_pct,
                pitch=pitch_str,
            )
            await communicate.save(temp_path)

            if self._stop_event.is_set():
                return

            # Play audio using native Windows MCI playback
            loop = asyncio.get_running_loop()
            played = await loop.run_in_executor(None, self._play_mp3_native, temp_path)
            if not played:
                # SAPI fallback if MCI fails
                await self._speak_pyttsx3(text)
        except Exception as e:
            log.warning("tts.edge_tts_error", error=str(e), fallback="sapi")
            await self._speak_pyttsx3(text)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _play_mp3_native(self, path: str) -> bool:
        """Play MP3 file using Windows MCI with instant interruption support."""
        try:
            import ctypes
            mci = ctypes.windll.winmm.mciSendStringW
            alias = f"woody_tts_{int(time.time() * 1000)}"
            err = mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, 0)
            if err != 0:
                err = mci(f'open "{path}" alias {alias}', None, 0, 0)
                if err != 0:
                    return False
            mci(f'play {alias}', None, 0, 0)

            # Poll status in short intervals so we can stop immediately if interrupted
            buf = ctypes.create_unicode_buffer(128)
            while not self._stop_event.is_set():
                mci(f'status {alias} mode', buf, 128, 0)
                mode = buf.value.strip().lower()
                if mode in ("stopped", ""):
                    break
                time.sleep(0.04)

            mci(f'stop {alias}', None, 0, 0)
            mci(f'close {alias}', None, 0, 0)
            return True
        except Exception as e:
            log.debug("tts.mci_playback_error", error=str(e))
            return False

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
        """Use Windows SAPI or pyttsx3 as a fast, reliable zero-config TTS engine."""
        import re
        # Clean markdown symbols before speaking out loud
        speech_text = re.sub(r'[*_#`~\[\]]', '', text).strip()
        if not speech_text:
            return

        # Strategy 1: Native Windows SAPI (ultra-fast, clear, thread-safe with CoInitialize)
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Volume = int(min(1.0, max(0.0, self._volume)) * 100)
                speaker.Rate = int(max(-10, min(10, (self._rate - 1.0) * 5)))
                speaker.Speak(speech_text)
                return
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            log.debug("tts.sapi_fallback_error", error=str(e))

        # Strategy 2: pyttsx3
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", int(engine.getProperty("rate") * self._rate))
            engine.setProperty("volume", self._volume)
            engine.say(speech_text)
            engine.runAndWait()
        except ImportError:
            log.warning(
                "tts.pyttsx3_not_installed",
                hint="pip install pyttsx3",
            )
        except Exception as e:
            log.error("tts.pyttsx3_error", error=str(e))

    # ── Control ──────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Stop any currently playing speech immediately."""
        self._stop_event.set()
        try:
            import ctypes
            ctypes.windll.winmm.mciSendStringW("stop all", None, 0, 0)
            ctypes.windll.winmm.mciSendStringW("close all", None, 0, 0)
        except Exception:
            pass
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Speak("", 2)  # SVSFPurgeBeforeSpeak = 2
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            pass
        self._speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    @property
    def voice(self) -> str:
        return self._voice

    @voice.setter
    def voice(self, value: str) -> None:
        self._voice = value

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str = "normal") -> None:
        """Switch TTS voice between normal mode (Avery) and cat/pet mode (community-blcuaurhzmvi)."""
        mode_clean = mode.lower().strip()
        self._mode = mode_clean
        if mode_clean in ("pet", "cat"):
            self._voice = self._pet_voice
            log.info("tts.mode_set_pet", voice=self._voice)
        else:
            self._voice = self._default_voice
            log.info("tts.mode_set_normal", voice=self._voice)

    def set_voice(self, voice_id: str) -> None:
        """Explicitly switch the active TTS voice."""
        self._voice = voice_id
        log.info("tts.voice_set", voice=voice_id)
