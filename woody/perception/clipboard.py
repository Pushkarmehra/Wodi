"""
Clipboard and drag-drop watcher.

Monitors the Windows clipboard for changes and emits events
so Woody can use clipboard content as context without a screenshot.

"Summarize this" → resolves to whatever is on the clipboard.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

from woody.utils.logging import get_logger

log = get_logger(__name__)


class ClipboardWatcher:
    """
    Polls the clipboard for changes and calls on_change when content updates.

    Usage:
        def on_clip(text: str):
            print("Clipboard:", text[:80])

        watcher = ClipboardWatcher(on_change=on_clip)
        watcher.start()
    """

    def __init__(
        self,
        on_change: Callable[[str], None] | None = None,
        poll_interval_ms: int = 500,
    ) -> None:
        self._on_change = on_change
        self._interval = poll_interval_ms / 1000.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_content: str = ""
        self._current_content: str = ""

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="Woody-clipboard")
        self._thread.start()
        log.info("clipboard.started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def get_current(self) -> str:
        """Return the current clipboard text content."""
        return self._current_content

    def _run(self) -> None:
        while self._running:
            text = self._read_clipboard()
            if text and text != self._last_content:
                self._last_content = text
                self._current_content = text
                log.debug("clipboard.changed", length=len(text))
                if self._on_change:
                    try:
                        self._on_change(text)
                    except Exception as e:
                        log.error("clipboard.callback_error", error=str(e))
            time.sleep(self._interval)

    def _read_clipboard(self) -> str:
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    return str(data)
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            # Fallback: use tkinter (no win32 dep)
            try:
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                text = root.clipboard_get()
                root.destroy()
                return text
            except Exception:
                return ""
        return ""
