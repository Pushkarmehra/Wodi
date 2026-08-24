import httpx
import aiohttp
import asyncio
import time

API_KEY = "WWZIN0t1enVEcFIwX01aQ3RVMy1jejNSaXRQUnZTNFA6Z1RYM0FwTk1IQmdfelUxRFJmQXVZNA=="
headers = {"Authorization": f"Basic {API_KEY}", "Content-Type": "application/json"}

async def test_opts():
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Prewarm
        await client.post("https://api.inworld.ai/tts/v1/voice", json={"text": "hi", "voiceId": "Avery", "modelId": "inworld-tts-2", "deliveryMode": "BALANCED", "language": "en-US", "audioConfig": {"speakingRate": 1.05}}, headers=headers)
        
        # Test 1: AUTO language + timestampType
        t0 = time.perf_counter()
        r1 = await client.post("https://api.inworld.ai/tts/v1/voice", json={"text": "Hello! I am Woody.", "voiceId": "Avery", "modelId": "inworld-tts-2", "deliveryMode": "CREATIVE", "language": "AUTO", "timestampType": "WORD", "audioConfig": {"speakingRate": 1.0}}, headers=headers)
        t1 = (time.perf_counter() - t0) * 1000
        print(f"Default (AUTO + WORD timestamp + CREATIVE): {t1:.1f}ms")

        # Test 2: en-US + No timestamp + BALANCED
        t0 = time.perf_counter()
        r2 = await client.post("https://api.inworld.ai/tts/v1/voice", json={"text": "Hello! I am Woody.", "voiceId": "Avery", "modelId": "inworld-tts-2", "deliveryMode": "BALANCED", "language": "en-US", "audioConfig": {"speakingRate": 1.05}}, headers=headers)
        t2 = (time.perf_counter() - t0) * 1000
        print(f"Optimized (en-US + no timestamp + BALANCED): {t2:.1f}ms")

        # Test 3: inworld-tts-1 vs inworld-tts-2
        for m in ["inworld-tts-1", "inworld-tts-1.5", "inworld-tts-2"]:
            t0 = time.perf_counter()
            r3 = await client.post("https://api.inworld.ai/tts/v1/voice", json={"text": "Hello! I am Woody.", "voiceId": "Avery", "modelId": m, "audioConfig": {"speakingRate": 1.05}}, headers=headers)
            t3 = (time.perf_counter() - t0) * 1000
            print(f"Model {m:16s}: {t3:.1f}ms (HTTP {r3.status_code})")

    # Test aiohttp client
    async with aiohttp.ClientSession(headers=headers) as session:
        t0 = time.perf_counter()
        async with session.post("https://api.inworld.ai/tts/v1/voice", json={"text": "Hello! I am Woody.", "voiceId": "Avery", "modelId": "inworld-tts-2", "deliveryMode": "BALANCED", "language": "en-US", "audioConfig": {"speakingRate": 1.05}}) as resp:
            await resp.json()
        t_aio = (time.perf_counter() - t0) * 1000
        print(f"aiohttp ClientSession (en-US + BALANCED): {t_aio:.1f}ms")

if __name__ == "__main__":
    asyncio.run(test_opts())
