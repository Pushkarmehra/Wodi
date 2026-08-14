"""Unit tests for episodic and semantic memory."""
from __future__ import annotations

import pytest
from pathlib import Path

from wodi.memory.episodic import EpisodicMemory
from wodi.memory.semantic import SemanticMemory, UserPreferences


class TestEpisodicMemory:
    def test_log_and_retrieve(self, tmp_path: Path):
        mem = EpisodicMemory(db_path=tmp_path / "test.db")
        mem.open()
        mem.log_session(
            session_id="test1",
            user_request="open notepad",
            result_summary="Opened Notepad",
            success=True,
        )
        sessions = mem.get_recent(n=5)
        assert len(sessions) == 1
        assert sessions[0]["user_request"] == "open notepad"
        mem.close()

    def test_multiple_sessions(self, tmp_path: Path):
        mem = EpisodicMemory(db_path=tmp_path / "test2.db")
        mem.open()
        for i in range(5):
            mem.log_session(f"sess{i}", f"request {i}", success=True)
        assert mem.get_session_count() == 5
        mem.close()

    def test_format_history_empty(self, tmp_path: Path):
        mem = EpisodicMemory(db_path=tmp_path / "test3.db")
        mem.open()
        assert mem.format_history_for_prompt() == ""
        mem.close()


class TestSemanticMemory:
    def test_save_and_load(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "prefs.json")
        prefs = mem.load()
        prefs.tone = "friendly"
        mem.save(prefs)

        mem2 = SemanticMemory(path=tmp_path / "prefs.json")
        loaded = mem2.load()
        assert loaded.tone == "friendly"

    def test_update_field(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "prefs2.json")
        mem.load()
        updated = mem.update(tone="technical")
        assert updated.tone == "technical"

    def test_default_preferences(self, tmp_path: Path):
        mem = SemanticMemory(path=tmp_path / "nonexistent_prefs.json")
        prefs = mem.load()
        assert prefs.tone == "concise"
        assert prefs.preferred_apps.browser == "chrome"
