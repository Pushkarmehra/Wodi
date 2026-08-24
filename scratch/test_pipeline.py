import asyncio
import re
import time

async def simulate_llm_stream():
    tokens = ["Hello", " there", "! ", "I ", "am ", "Woody", ", ", "your ", "personal ", "AI ", "assistant", ". ", "I ", "can ", "help ", "you ", "manage ", "files", ", ", "search ", "the ", "web", ", ", "and ", "automate ", "desktop ", "tasks", "."]
    for tok in tokens:
        await asyncio.sleep(0.06)
        yield tok

async def main():
    t0 = time.perf_counter()
    sentence_buf = ""
    async for chunk in simulate_llm_stream():
        sentence_buf += chunk
        m = re.search(r'([.!?\n])\s+', sentence_buf)
        if m:
            sent = sentence_buf[:m.end()].strip()
            sentence_buf = sentence_buf[m.end():]
            t = (time.perf_counter() - t0) * 1000
            print(f"[{t:.0f}ms] Extracted sentence for immediate TTS: '{sent}'")
    if sentence_buf.strip():
        t = (time.perf_counter() - t0) * 1000
        print(f"[{t:.0f}ms] Extracted final sentence: '{sentence_buf.strip()}'")

if __name__ == "__main__":
    asyncio.run(main())
