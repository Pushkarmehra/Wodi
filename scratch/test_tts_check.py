import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from woody.synthesis.tts import TTSEngine

async def test_tts():
    print("Testing Inworld TTS...")
    tts = TTSEngine(
        engine="inworld",
        voice=os.getenv("INWORLD_VOICE", "Hades"),
        inworld_api_key=os.getenv("INWORLD_API_KEY", ""),
        inworld_model=os.getenv("INWORLD_MODEL", "inworld-tts-2"),
    )
    tts.load()
    print("Engine loaded:", tts.engine)
    chunk = await tts._synthesize_inworld_chunk("Testing audio output.")
    if chunk:
        print(f"Inworld synth successful: {len(chunk)} bytes received.")
    else:
        print("Inworld synth returned None! Testing edge-tts fallback...")
        tts_edge = TTSEngine(engine="edge-tts", voice="en-US-AriaNeural")
        tts_edge.load()
        print("Edge TTS loaded.")

if __name__ == "__main__":
    asyncio.run(test_tts())
