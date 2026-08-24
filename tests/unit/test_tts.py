"""Unit tests for TTS engine and sentence streaming."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from woody.synthesis.tts import TTSEngine


class TestTTSEngine:
    def test_clean_for_speech(self):
        tts = TTSEngine(engine="disabled")
        cleaned = tts._clean_for_speech("Hello **world**! Visit https://example.com for info.")
        assert "world" in cleaned
        assert "**" not in cleaned
        assert "https://" not in cleaned
        assert "the web link" in cleaned

    def test_split_into_sentences(self):
        tts = TTSEngine(engine="disabled")
        sentences = tts._split_into_sentences("Hello world! How are you today? I am Woody.")
        assert len(sentences) >= 2

    @pytest.mark.asyncio
    async def test_speak_sentence_stream_execution(self):
        tts = TTSEngine(engine="disabled")
        q = asyncio.Queue()
        await q.put("First sentence.")
        await q.put("Second sentence.")
        await q.put(None)

        # Should complete cleanly without NameError or crash
        await tts.speak_sentence_stream(q)

    @pytest.mark.asyncio
    async def test_speak_sentence_stream_with_mock_playback(self):
        tts = TTSEngine(engine="pyttsx3")
        with patch.object(tts, "_speak_pyttsx3", return_value=None):
            q = asyncio.Queue()
            await q.put("Hello from Woody assistant.")
            await q.put(None)

            await tts.speak_sentence_stream(q)

    def test_stop(self):
        tts = TTSEngine(engine="disabled")
        tts.stop()
        assert not tts.is_speaking
