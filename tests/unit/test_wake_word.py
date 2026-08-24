"""Unit tests for WakeWordDetector phrase matching and callback firing."""
from __future__ import annotations

import pytest
from woody.perception.wake_word import WakeWordDetector


class TestWakeWordDetector:
    def test_phrase_pattern_matches_variations(self):
        detector = WakeWordDetector(phrase="hey woody")
        assert detector._phrase_re.search("hey woody")
        assert detector._phrase_re.search("Hey Woody, open chrome")
        assert detector._phrase_re.search("Hi Woody")
        assert detector._phrase_re.search("Hello Woody")
        assert detector._phrase_re.search("Woody, what time is it?")
        assert detector._phrase_re.search("ok woody")

    def test_callback_fires(self):
        fired = []
        detector = WakeWordDetector(phrase="hey woody", on_wake=lambda: fired.append(True))
        detector._fire_callback()
        assert len(fired) == 1
