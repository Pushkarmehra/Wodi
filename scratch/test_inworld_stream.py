import asyncio
import base64
import json
import os
import tempfile
import time
import ctypes
import httpx

API_KEY = "WWZIN0t1enVEcFIwX01aQ3RVMy1jejNSaXRQUnZTNFA6Z1RYM0FwTk1IQmdfelUxRFJmQXVZNA=="

async def test_streaming():
    url = "https://api.inworld.ai/tts/v1/voice:stream"
    headers = {
        "Authorization": f"Basic {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": "Woody is now connected to Inworld Text to Speech streaming API with the Avery voice.",
        "voice_id": "Avery",
        "model_id": "inworld-tts-2",
        "audio_config": {
            "audio_encoding": "MP3",
            "speaking_rate": 1
        },
        "delivery_mode": "CREATIVE",
        "language": "AUTO"
    }

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        temp_path = f.name

    try:
        mp3_file = open(temp_path, "wb")
        chunks = 0
        async with httpx.AsyncClient(timeout=15.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                print(f"HTTP Status: {response.status_code}")
                if response.status_code != 200:
                    body = await response.aread()
                    print("Error response:", body.decode('utf-8', errors='ignore'))
                    return

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "result" in data and "audioContent" in data["result"]:
                            audio_chunk = base64.b64decode(data["result"]["audioContent"])
                            mp3_file.write(audio_chunk)
                            chunks += 1
                    except Exception as e:
                        print("NDJSON parse error:", e)

        mp3_file.close()
        file_size = os.path.getsize(temp_path)
        print(f"Stream complete: received {chunks} chunks, {file_size} bytes.")

        # Play via MCI
        mci = ctypes.windll.winmm.mciSendStringW
        alias = f"inworld_stream_{int(time.time() * 1000)}"
        mci(f'open "{temp_path}" type mpegvideo alias {alias}', None, 0, 0)
        mci(f'play {alias}', None, 0, 0)
        buf = ctypes.create_unicode_buffer(128)
        while True:
            mci(f'status {alias} mode', buf, 128, 0)
            mode = buf.value.strip().lower()
            if mode in ('stopped', ''):
                break
            await asyncio.sleep(0.04)
        mci(f'stop {alias}', None, 0, 0)
        mci(f'close {alias}', None, 0, 0)
        print("Playback finished!")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(test_streaming())
