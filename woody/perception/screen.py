"""
Event-driven screen capture for Woody.

Uses Win32 SetWinEventHook to capture only on window focus change,
keeping idle CPU near zero (vs. polling screenshots on a timer).

On non-Windows platforms or if Win32 hooks fail, falls back to
interval-based polling via mss.

Returns PIL.Image captures with monitor metadata.
"""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from woody.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class ScreenCapture:
    image: Any         # PIL.Image.Image
    monitor: dict      # {"left": x, "top": y, "width": w, "height": h}
    window_title: str
    timestamp: float


class ScreenWatcher:
    """
    Watches for window focus changes and captures the active window region.

    Usage:
        def on_capture(capture: ScreenCapture):
            capture.image.save("shot.png")

        watcher = ScreenWatcher(on_capture=on_capture, event_driven=True)
        watcher.start()
        # ... later ...
        watcher.stop()

    Also supports manual one-shot capture via capture_now().
    """

    def __init__(
        self,
        on_capture: Callable[[ScreenCapture], None] | None = None,
        event_driven: bool = True,
        poll_interval_ms: int = 500,
        capture_region: str = "active_window",  # "full" | "active_window"
    ) -> None:
        self._on_capture = on_capture
        self._event_driven = event_driven
        self._poll_interval = poll_interval_ms / 1000.0
        self._capture_region = capture_region
        self._running = False
        self._thread: threading.Thread | None = None
        self._hook: Any = None
        self._last_hwnd: int = 0

    def start(self) -> None:
        self._running = True
        if self._event_driven and self._try_win32_hook():
            log.info("screen.started", mode="win32_event_hook")
        else:
            self._thread = threading.Thread(
                target=self._poll_loop, daemon=True, name="Woody-screen-poll"
            )
            self._thread.start()
            log.info("screen.started", mode="poll", interval_ms=int(self._poll_interval * 1000))

    def stop(self) -> None:
        self._running = False
        self._unhook_win32()
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("screen.stopped")

    def capture_now(self, region: str | None = None) -> ScreenCapture | None:
        """Take a one-shot capture of the active window (or full desktop)."""
        return self._capture(region or self._capture_region)

    # ── Win32 Event Hook ──────────────────────────────────────────────────────

    def _try_win32_hook(self) -> bool:
        """Install SetWinEventHook for EVENT_SYSTEM_FOREGROUND. Returns True on success."""
        try:
            import win32con
            import win32gui
            import win32event
        except ImportError:
            log.debug("screen.win32_unavailable", fallback="poll")
            return False

        try:
            WinEventProc = ctypes.WINFUNCTYPE(
                None,
                ctypes.wintypes.HANDLE,   # hWinEventHook
                ctypes.wintypes.DWORD,    # event
                ctypes.wintypes.HWND,     # hwnd
                ctypes.wintypes.LONG,     # idObject
                ctypes.wintypes.LONG,     # idChild
                ctypes.wintypes.DWORD,    # dwEventThread
                ctypes.wintypes.DWORD,    # dwmsEventTime
            )

            def _callback(hook, event, hwnd, id_obj, id_child, event_thread, event_time):
                if hwnd and hwnd != self._last_hwnd:
                    self._last_hwnd = hwnd
                    # Capture on a background thread to not block the hook
                    threading.Thread(
                        target=self._on_focus_change, args=(hwnd,), daemon=True
                    ).start()

            self._win_proc = WinEventProc(_callback)

            user32 = ctypes.windll.user32
            EVENT_SYSTEM_FOREGROUND = 0x0003
            WINEVENT_OUTOFCONTEXT = 0x0000

            self._hook = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                0,
                self._win_proc,
                0,
                0,
                WINEVENT_OUTOFCONTEXT,
            )

            if not self._hook:
                log.warning("screen.hook_failed", fallback="poll")
                return False

            # Pump Win32 message queue on a dedicated thread
            self._hook_thread = threading.Thread(
                target=self._message_pump, daemon=True, name="Woody-screen-hook"
            )
            self._hook_thread.start()
            return True

        except Exception as e:
            log.warning("screen.hook_error", error=str(e), fallback="poll")
            return False

    def _message_pump(self) -> None:
        """Windows message pump to keep the hook alive."""
        try:
            import win32gui
            msg = ctypes.wintypes.MSG()
            while self._running:
                if ctypes.windll.user32.PeekMessageW(
                    ctypes.byref(msg), None, 0, 0, 1  # PM_REMOVE
                ):
                    ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                    ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.01)
        except Exception as e:
            log.error("screen.message_pump_error", error=str(e))

    def _unhook_win32(self) -> None:
        if self._hook:
            try:
                ctypes.windll.user32.UnhookWinEvent(self._hook)
            except Exception:
                pass
            self._hook = None

    def _on_focus_change(self, hwnd: int) -> None:
        capture = self._capture(self._capture_region, hwnd=hwnd)
        if capture and self._on_capture:
            self._on_capture(capture)

    # ── Poll Loop (fallback) ──────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        import time
        while self._running:
            capture = self._capture(self._capture_region)
            if capture and self._on_capture:
                self._on_capture(capture)
            time.sleep(self._poll_interval)

    # ── Capture Logic ─────────────────────────────────────────────────────────

    def _capture(self, region: str, hwnd: int | None = None) -> ScreenCapture | None:
        try:
            from PIL import Image
            import mss

            window_title = self._get_window_title(hwnd)

            if region == "active_window" and hwnd:
                rect = self._get_window_rect(hwnd)
                if rect:
                    with mss.mss() as sct:
                        shot = sct.grab(rect)
                        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    return ScreenCapture(
                        image=img,
                        monitor=rect,
                        window_title=window_title,
                        timestamp=time.time(),
                    )

            # Full desktop fallback
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # Combined all-monitors rect
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            return ScreenCapture(
                image=img,
                monitor=dict(monitor),
                window_title=window_title,
                timestamp=time.time(),
            )

        except Exception as e:
            log.debug("screen.capture_error", error=str(e))
            return None

    def _get_window_rect(self, hwnd: int) -> dict | None:
        try:
            import win32gui
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right - left < 10 or bottom - top < 10:
                return None
            return {"left": left, "top": top, "width": right - left, "height": bottom - top}
        except Exception:
            return None

    def _get_window_title(self, hwnd: int | None) -> str:
        try:
            import win32gui
            if hwnd:
                return win32gui.GetWindowText(hwnd)
            return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        except Exception:
            return ""
