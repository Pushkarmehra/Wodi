import asyncio
import base64
import time
import httpx

API_KEY = "WWZIN0t1enVEcFIwX01aQ3RVMy1jejNSaXRQUnZTNFA6Z1RYM0FwTk1IQmdfelUxRFJmQXVZNA=="
headers = {"Authorization": f"Basic {API_KEY}", "Content-Type": "application/json"}

async def test_concurrent_fetch():
    client = httpx.AsyncClient(timeout=15.0, limits=httpx.Limits(max_keepalive_connections=10, max_connections=20))
    sentences = [
        "Hello! I am Woody, your Windows AI assistant.",
        "I can help you search the web, control your apps, and manage files.",
        "Let's get started right now!"
    ]

    async def fetch_one(idx, sent):
        t0 = time.perf_counter()
        payload = {
            "text": sent,
            "voiceId": "Avery",
            "modelId": "inworld-tts-2",
            "deliveryMode": "CREATIVE",
            "language": "AUTO",
            "audioConfig": {"speakingRate": 1.05}
        }
        resp = await client.post("https://api.inworld.ai/tts/v1/voice", json=payload, headers=headers)
        ms = (time.perf_counter() - t0) * 1000
        print(f"Sentence {idx} fetched in {ms:.0f}ms (HTTP {resp.status_code})")
        if resp.status_code == 200:
            return base64.b64decode(resp.json()["audioContent"])
        return None

    # Test concurrent dispatch
    t_start = time.perf_counter()
    tasks = [fetch_one(i+1, s) for i, s in enumerate(sentences)]
    results = await asyncio.gather(*tasks)
    total_time = (time.perf_counter() - t_start) * 1000
    print(f"All 3 sentences fetched in parallel in {total_time:.0f}ms total (avg {(total_time/len(sentences)):.0f}ms/sent)!")
    await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_concurrent_fetch())
