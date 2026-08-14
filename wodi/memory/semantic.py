"""
Semantic Memory — Structured user preference profile.

User-editable JSON/Pydantic schema so preferences are transparent and
controllable, not a silent black box.

Stored at: ~/.wodi/preferences.json
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field
from wodi.utils.logging import get_logger

log = get_logger(__name__)


class AppPreferences(BaseModel):
    browser: str = "chrome"
    editor: str = "vscode"
    terminal: str = "windows terminal"
    music: str = ""
    email: str = ""


class UserPreferences(BaseModel):
    """User preference profile — editable via Settings UI or directly in JSON."""
    name: str = ""
    tone: str = "concise"           # concise | verbose | friendly | technical
    tts_rate: float = 1.0
    tts_volume: float = 0.85
    tts_voice: str = "en_US-lessac-medium"
    preferred_apps: AppPreferences = Field(default_factory=AppPreferences)
    frequent_commands: list[str] = Field(default_factory=list)
    disallowed_apps: list[str] = Field(default_factory=list)    # Never open these
    time_format: str = "12h"        # 12h | 24h
    confirmation_required: list[str] = Field(default_factory=list)  # Always confirm these tools


class SemanticMemory:
    """
    Reads and writes the user preference profile.

    Usage:
        mem = SemanticMemory(path="~/.wodi/preferences.json")
        prefs = mem.load()
        prefs.tone = "friendly"
        mem.save(prefs)
    """

    def __init__(self, path: str | Path = "~/.wodi/preferences.json") -> None:
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._prefs: UserPreferences | None = None

    def load(self) -> UserPreferences:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                self._prefs = UserPreferences(**data)
                log.debug("semantic.loaded", path=str(self._path))
                return self._prefs
            except Exception as e:
                log.warning("semantic.load_error", error=str(e), fallback="defaults")
        self._prefs = UserPreferences()
        return self._prefs

    def save(self, prefs: UserPreferences | None = None) -> None:
        p = prefs or self._prefs
        if p is None:
            return
        self._prefs = p
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(p.model_dump(), f, indent=2)
        log.debug("semantic.saved", path=str(self._path))

    def get(self) -> UserPreferences:
        if self._prefs is None:
            return self.load()
        return self._prefs

    def update(self, **kwargs: object) -> UserPreferences:
        prefs = self.get()
        for key, val in kwargs.items():
            if hasattr(prefs, key):
                setattr(prefs, key, val)
        self.save(prefs)
        return prefs

    def format_for_prompt(self) -> str:
        """Format preferences for inclusion in the synthesizer prompt."""
        p = self.get()
        lines = [
            f"User name: {p.name or 'not set'}",
            f"Preferred tone: {p.tone}",
            f"Preferred apps: browser={p.preferred_apps.browser}, editor={p.preferred_apps.editor}",
        ]
        if p.frequent_commands:
            lines.append(f"Frequent commands: {', '.join(p.frequent_commands[:5])}")
        return "\n".join(lines)
