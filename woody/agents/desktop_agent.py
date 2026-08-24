"""
Desktop Agent — Win32/UIAutomation desktop control.

Handles all native Windows desktop automation:
  - open_app / close_app / focus_window / switch_window
  - type_text / press_key / hotkey
  - get_open_windows / get_window_info
  - take_screenshot (triggers screen capture)
  - move_mouse / click / right_click / double_click
  - scroll

Uses pywinauto (preferred) with pyautogui/pywin32 as fallback layers.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Any

from woody.agents.base_agent import AgentResult, BaseAgent
from woody.utils.logging import get_logger

log = get_logger(__name__)

from woody.tools.builtin.desktop_tools import APP_ALIASES, find_windows_app


class DesktopAgent(BaseAgent):
    """
    Specialist agent for Windows desktop automation.
    Phase 1 primary agent — fully implemented.
    """

    AGENT_NAME = "desktop_agent"
    ALLOWED_ACTIONS = {
        "open_app",
        "close_app",
        "focus_window",
        "switch_window",
        "type_text",
        "press_key",
        "hotkey",
        "click",
        "right_click",
        "double_click",
        "scroll",
        "move_mouse",
        "get_open_windows",
        "get_window_info",
        "take_screenshot",
        "minimize_window",
        "maximize_window",
        "restore_window",
        "resize_window",
        "clarify",
        "compose_email",
        "get_user_profile",
        "set_user_profile",
    }

    def __init__(self, confirm_callback: Any | None = None) -> None:
        super().__init__(max_retries=2, confirm_callback=confirm_callback)

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        """Dispatch to the appropriate desktop action handler."""
        handlers = {
            "open_app": self._open_app,
            "close_app": self._close_app,
            "focus_window": self._focus_window,
            "switch_window": self._switch_window,
            "type_text": self._type_text,
            "press_key": self._press_key,
            "hotkey": self._hotkey,
            "click": self._click,
            "right_click": self._right_click,
            "double_click": self._double_click,
            "scroll": self._scroll,
            "move_mouse": self._move_mouse,
            "get_open_windows": self._get_open_windows,
            "get_window_info": self._get_window_info,
            "take_screenshot": self._take_screenshot,
            "minimize_window": self._minimize_window,
            "maximize_window": self._maximize_window,
            "restore_window": self._restore_window,
            "resize_window": self._resize_window,
            "clarify": self._clarify,
            "compose_email": self._compose_email,
            "get_user_profile": self._get_user_profile,
            "set_user_profile": self._set_user_profile,
        }
        handler = handlers.get(action)
        if not handler:
            return AgentResult(success=False, output=None, error=f"Unknown action: {action}")

        return await handler(params, context)

    # ── Action Implementations ────────────────────────────────────────────────

    async def _open_app(self, params: dict, context: dict) -> AgentResult:
        from woody.tools.builtin.desktop_tools import open_app as launch_app

        app_name = params.get("app_name", "").strip()
        if not app_name:
            return AgentResult(success=False, output=None, error="No application name provided.")

        log.info("desktop.open_app", app=app_name)
        res = launch_app(app_name)
        if res.get("success"):
            return AgentResult(success=True, output=res.get("message", f"Opened {app_name}"))
        else:
            return AgentResult(success=False, output=None, error=res.get("error", f"Could not open {app_name}"))

    async def _close_app(self, params: dict, context: dict) -> AgentResult:
        app_name = params.get("app_name", "").lower().strip()
        exe = APP_ALIASES.get(app_name, app_name).replace(".exe", "")
        try:
            import psutil
            killed = []
            for proc in psutil.process_iter(["name", "pid"]):
                if exe.lower() in proc.info["name"].lower():
                    proc.terminate()
                    killed.append(proc.info["name"])
            if killed:
                return AgentResult(success=True, output=f"Closed: {', '.join(killed)}")
            return AgentResult(success=False, output=None, error=f"No running process matching '{app_name}'")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _focus_window(self, params: dict, context: dict) -> AgentResult:
        title = params.get("title", "") or params.get("app_name", "")
        try:
            import win32gui
            import win32con

            def _find_and_focus(hwnd: int, _: Any) -> None:
                if win32gui.IsWindowVisible(hwnd):
                    wtext = win32gui.GetWindowText(hwnd)
                    if title.lower() in wtext.lower():
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)

            win32gui.EnumWindows(_find_and_focus, None)
            return AgentResult(success=True, output=f"Focused window: {title}")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _switch_window(self, params: dict, context: dict) -> AgentResult:
        return await self._focus_window(params, context)

    async def _type_text(self, params: dict, context: dict) -> AgentResult:
        text = params.get("text", "")
        delay = float(params.get("delay", 0.03))
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=delay)
            return AgentResult(success=True, output=f"Typed {len(text)} characters")
        except Exception:
            # Fallback: pyperclip + ctrl+v paste
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                import pyautogui
                pyautogui.hotkey("ctrl", "v")
                return AgentResult(success=True, output=f"Pasted {len(text)} characters (paste method)")
            except Exception as e:
                return AgentResult(success=False, output=None, error=str(e))

    async def _press_key(self, params: dict, context: dict) -> AgentResult:
        key = params.get("key", "")
        try:
            import pyautogui
            pyautogui.press(key)
            return AgentResult(success=True, output=f"Pressed key: {key}")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _hotkey(self, params: dict, context: dict) -> AgentResult:
        keys = params.get("keys", [])
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.replace("+", ",").split(",")]
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            return AgentResult(success=True, output=f"Hotkey: {'+'.join(keys)}")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _click(self, params: dict, context: dict) -> AgentResult:
        x = params.get("x")
        y = params.get("y")
        element_name = params.get("element_name")
        try:
            import pyautogui
            if element_name:
                # Try UI tree element targeting first
                coords = self._find_element_coords(element_name)
                if coords:
                    x, y = coords
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y))
                return AgentResult(success=True, output=f"Clicked ({x}, {y})")
            return AgentResult(success=False, output=None, error="No coordinates or element found")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _right_click(self, params: dict, context: dict) -> AgentResult:
        x, y = params.get("x", 0), params.get("y", 0)
        try:
            import pyautogui
            pyautogui.rightClick(int(x), int(y))
            return AgentResult(success=True, output=f"Right-clicked ({x}, {y})")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _double_click(self, params: dict, context: dict) -> AgentResult:
        x, y = params.get("x", 0), params.get("y", 0)
        element_name = params.get("element_name")
        try:
            import pyautogui
            if element_name:
                coords = self._find_element_coords(element_name)
                if coords:
                    x, y = coords
            pyautogui.doubleClick(int(x), int(y))
            return AgentResult(success=True, output=f"Double-clicked ({x}, {y})")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _scroll(self, params: dict, context: dict) -> AgentResult:
        clicks = params.get("clicks", 3)
        direction = params.get("direction", "down")
        amount = -abs(int(clicks)) if direction == "down" else abs(int(clicks))
        try:
            import pyautogui
            pyautogui.scroll(amount)
            return AgentResult(success=True, output=f"Scrolled {direction} {abs(clicks)} clicks")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _move_mouse(self, params: dict, context: dict) -> AgentResult:
        x, y = params.get("x", 0), params.get("y", 0)
        duration = float(params.get("duration", 0.2))
        try:
            import pyautogui
            pyautogui.moveTo(int(x), int(y), duration=duration)
            return AgentResult(success=True, output=f"Moved mouse to ({x}, {y})")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _get_open_windows(self, params: dict, context: dict) -> AgentResult:
        try:
            import win32gui

            windows = []

            def _enum(hwnd: int, _: Any) -> None:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        windows.append({"hwnd": hwnd, "title": title})

            win32gui.EnumWindows(_enum, None)
            return AgentResult(success=True, output=windows)
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _get_window_info(self, params: dict, context: dict) -> AgentResult:
        title = params.get("title", "")
        try:
            import win32gui
            hwnd = win32gui.FindWindow(None, title) if title else win32gui.GetForegroundWindow()
            rect = win32gui.GetWindowRect(hwnd)
            return AgentResult(success=True, output={
                "hwnd": hwnd,
                "title": win32gui.GetWindowText(hwnd),
                "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]},
            })
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _take_screenshot(self, params: dict, context: dict) -> AgentResult:
        try:
            from woody.tools.builtin.desktop_tools import take_screenshot
            res = take_screenshot(params.get("region"))
            if res.get("success"):
                return AgentResult(success=True, output=res.get("message", f"Screenshot saved to {res.get('path')}"))
            return AgentResult(success=False, output=None, error=res.get("error", "Screenshot capture failed"))
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _minimize_window(self, params: dict, context: dict) -> AgentResult:
        return await self._window_state_change(params, "minimize")

    async def _maximize_window(self, params: dict, context: dict) -> AgentResult:
        return await self._window_state_change(params, "maximize")

    async def _restore_window(self, params: dict, context: dict) -> AgentResult:
        return await self._window_state_change(params, "restore")

    async def _window_state_change(self, params: dict, state: str) -> AgentResult:
        title = params.get("title", "")
        try:
            import win32gui, win32con
            hwnd = win32gui.FindWindow(None, title) if title else win32gui.GetForegroundWindow()
            cmd = {
                "minimize": win32con.SW_MINIMIZE,
                "maximize": win32con.SW_MAXIMIZE,
                "restore": win32con.SW_RESTORE,
            }[state]
            win32gui.ShowWindow(hwnd, cmd)
            return AgentResult(success=True, output=f"Window {state}d")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _resize_window(self, params: dict, context: dict) -> AgentResult:
        title = params.get("title", "")
        width = params.get("width", 800)
        height = params.get("height", 600)
        try:
            import win32gui
            hwnd = win32gui.FindWindow(None, title) if title else win32gui.GetForegroundWindow()
            rect = win32gui.GetWindowRect(hwnd)
            win32gui.MoveWindow(hwnd, rect[0], rect[1], width, height, True)
            return AgentResult(success=True, output=f"Resized to {width}x{height}")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _clarify(self, params: dict, context: dict) -> AgentResult:
        message = params.get("message", "Could you clarify your request?")
        return AgentResult(success=True, output={"clarification_needed": True, "message": message})

    async def _compose_email(self, params: dict, context: dict) -> AgentResult:
        from woody.tools.builtin.desktop_tools import compose_email
        to = params.get("to", "").strip()
        subject = params.get("subject", "").strip()
        body = params.get("body", "").strip()
        client = params.get("client", "default").strip()
        res = compose_email(to=to, subject=subject, body=body, client=client)
        if res.get("success"):
            return AgentResult(success=True, output=res.get("message", f"Opened email to {to}"))
        return AgentResult(success=False, output=None, error=res.get("error", "Failed to compose email"))

    async def _get_user_profile(self, params: dict, context: dict) -> AgentResult:
        from woody.tools.builtin.desktop_tools import get_user_profile
        res = get_user_profile()
        return AgentResult(success=res.get("success", False), output=res)

    async def _set_user_profile(self, params: dict, context: dict) -> AgentResult:
        from woody.tools.builtin.desktop_tools import set_user_profile
        name = params.get("name", "")
        tone = params.get("tone", "")
        preferred_email_app = params.get("preferred_email_app", "")
        res = set_user_profile(name=name, tone=tone, preferred_email_app=preferred_email_app)
        return AgentResult(success=res.get("success", False), output=res.get("message", "Profile updated"))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _find_element_coords(self, element_name: str) -> tuple[int, int] | None:
        """Use UI Automation to find element coordinates by name."""
        try:
            from woody.perception.ui_tree import UITreeWatcher
            watcher = UITreeWatcher()
            elem = watcher.find_element(name=element_name)
            if elem:
                return elem.center
        except Exception as e:
            log.debug("desktop.find_element_error", error=str(e))
        return None
