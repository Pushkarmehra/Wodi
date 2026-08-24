import asyncio
import base64
import json
import os
import re
import tempfile
import time
import ctypes
import httpx

API_KEY = "WWZIN0t1enVEcFIwX01aQ3RVMy1jejNSaXRQUnZTNFA6Z1RYM0FwTk1IQmdfelUxRFJmQXVZNA=="

class PipelinedInworldTTS:
    def __init__(self, api_key: str = API_KEY):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            timeout=20.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        self.stop_event = asyncio.Event()

    async def prewarm(self):
        """Warm up connection pool."""
        try:
            headers = {"Authorization": f"Basic {self.api_key}", "Content-Type": "application/json"}
            await self.client.post(
                "https://api.inworld.ai/tts/v1/voice",
                json={
                    "text": "hi",
                    "voiceId": "Avery",
                    "modelId": "inworld-tts-2",
                    "deliveryMode": "CREATIVE",
                    "language": "AUTO",
                    "audioConfig": {"speakingRate": 1.0}
                },
                headers=headers
            )
        except Exception:
            pass

    async def synthesize_sentence(self, text: str) -> bytes | None:
        """Synthesize a single sentence and return MP3 bytes."""
        if not text.strip():
            return None
        headers = {"Authorization": f"Basic {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "text": text,
            "voiceId": "Avery",
            "modelId": "inworld-tts-2",
            "deliveryMode": "CREATIVE",
            "language": "AUTO",
            "audioConfig": {"speakingRate": 1.05}
        }
        resp = await self.client.post("https://api.inworld.ai/tts/v1/voice", json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if "audioContent" in data:
                return base64.b64decode(data["audioContent"])
        return None

    def play_mp3_sync(self, mp3_bytes: bytes) -> None:
        """Play MP3 bytes via MCI."""
        if not mp3_bytes or self.stop_event.is_set():
            return
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(mp3_bytes)
            temp_path = f.name
        try:
            mci = ctypes.windll.winmm.mciSendStringW
            alias = f"piped_{int(time.time() * 1000)}"
            mci(f'open "{temp_path}" type mpegvideo alias {alias}', None, 0, 0)
            mci(f'play {alias}', None, 0, 0)
            buf = ctypes.create_unicode_buffer(128)
            while not self.stop_event.is_set():
                mci(f'status {alias} mode', buf, 128, 0)
                mode = buf.value.strip().lower()
                if mode in ("stopped", ""):
                    break
                time.sleep(0.03)
            mci(f'stop {alias}', None, 0, 0)
            mci(f'close {alias}', None, 0, 0)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    async def speak_stream(self, sentence_queue: asyncio.Queue[str | None]):
        """
        Consumes sentences from sentence_queue as they arrive,
        synthesizes them with prefetching, and plays them sequentially.
        """
        synth_queue = asyncio.Queue()

        async def _synthesizer_worker():
            while True:
                sentence = await sentence_queue.get()
                if sentence is None or self.stop_event.is_set():
                    await synth_queue.put(None)
                    break
                t0 = time.perf_counter()
                audio = await self.synthesize_sentence(sentence)
                latency = (time.perf_counter() - t0) * 1000
                print(f"[Synthesizer] Sentence: '{sentence[:30]}...' synthesized in {latency:.0f}ms")
                await synth_queue.put(audio)

        async def _player_worker():
            loop = asyncio.get_running_loop()
            while True:
                audio = await synth_queue.get()
                if audio is None or self.stop_event.is_set():
                    break
                print("[Player] Playing audio chunk...")
                await loop.run_in_executor(None, self.play_mp3_sync, audio)

        await asyncio.gather(_synthesizer_worker(), _player_worker())

async def main():
    tts = PipelinedInworldTTS()
    await tts.prewarm()
    print("Prewarmed connection pool!")

    queue = asyncio.Queue()

    async def _producer():
        # Simulate LLM producing sentences with small delays
        sentences = [
            "Hello! I am Woody, your AI assistant.",
            "I can help you search the web, control your apps, and manage files.",
            "Let's get started!"
        ]
        for s in sentences:
            await asyncio.sleep(0.3)
            print(f"[LLM] Streamed sentence: '{s}'")
            await queue.put(s)
        await queue.put(None)

    await asyncio.gather(_producer(), tts.speak_stream(queue))

if __name__ == "__main__":
    asyncio.run(main())
