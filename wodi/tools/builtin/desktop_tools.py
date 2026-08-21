"""
Built-in Desktop Tools — MCP tool server functions for Windows desktop automation.
These are called directly by the MCP host dispatcher.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Ordered list for deterministic schema registration
TOOLS = [
    "open_app",
    "close_app",
    "focus_window",
    "type_text",
    "press_key",
    "get_open_windows",
    "take_screenshot",
]

# Allowlist of known safe executables.  open_app ONLY launches apps in this list,
# preventing command injection when the user supplies arbitrary text.
APP_ALIASES: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "explorer": "explorer.exe",
    "vscode": "code.exe",
    "code": "code.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "paint": "mspaint.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "notepad++": "notepad++.exe",
    "spotify": "spotify.exe",
    "vlc": "vlc.exe",
    "discord": "discord.exe",
    "slack": "slack.exe",
    "teams": "ms-teams.exe",
    "zoom": "zoom.exe",
    "obs": "obs64.exe",
}


def open_app(app_name: str) -> dict:
    """Open an application by name.

    Args:
        app_name: Name of the application to open (e.g. 'notepad', 'chrome', 'calculator').
    """
    name_lower = app_name.lower().strip()
    exe = APP_ALIASES.get(name_lower)

    if exe is None:
        # Not in the safe allowlist — reject to prevent command injection
        suggestions = ", ".join(sorted(APP_ALIASES.keys()))
        return {
            "success": False,
            "error": (
                f"'{app_name}' is not in the allowed application list. "
                f"Supported: {suggestions}"
            ),
        }

    try:
        # shell=False — exe is from the safe allowlist, not raw user input
        subprocess.Popen([exe], shell=False)
        return {"success": True, "message": f"Opened {app_name} ({exe})."}
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"{exe} not found. The application may not be installed.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def close_app(app_name: str) -> dict:
    """Terminate all running processes matching an application name.

    Args:
        app_name: Name of the application to close (e.g. 'notepad', 'chrome').
    """
    try:
        import psutil

        name_lower = app_name.lower().strip()
        exe = APP_ALIASES.get(name_lower, app_name)
        # Strip .exe so we can do a flexible substring match on process names
        base_name = exe.lower().removesuffix(".exe")

        killed: list[str] = []
        for p in psutil.process_iter(["name", "pid"]):
            try:
                proc_name = (p.info.get("name") or "").lower()
                if base_name in proc_name:
                    p.terminate()
                    killed.append(p.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if killed:
            return {"success": True, "closed": killed}
        return {"success": False, "error": f"No running process found matching '{app_name}'."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_window(title: str) -> dict:
    """Bring a window to the foreground by its title.

    Args:
        title: Exact title of the window to focus.
    """
    try:
        import win32gui
        import win32con

        hwnd = win32gui.FindWindow(None, title)
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return {"success": True, "hwnd": hwnd}
        return {"success": False, "error": f"Window '{title}' not found."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_text(text: str, interval: float = 0.03) -> dict:
    """Type a string of text using keyboard automation.

    Args:
        text: The text to type.
        interval: Delay in seconds between each keystroke (default 0.03).
    """
    try:
        import pyautogui

        pyautogui.typewrite(text, interval=interval)
        return {"success": True, "chars": len(text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_key(key: str) -> dict:
    """Simulate pressing a single keyboard key.

    Args:
        key: The key name to press (e.g. 'enter', 'escape', 'tab', 'f5').
    """
    try:
        import pyautogui

        pyautogui.press(key)
        return {"success": True, "key": key}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_open_windows() -> dict:
    """Get a list of all currently visible, titled windows.

    Returns a list of dicts with 'hwnd' and 'title' keys.
    """
    try:
        import win32gui

        windows: list[dict] = []

        def _enum(hwnd: int, _: Any) -> None:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    windows.append({"hwnd": hwnd, "title": title})

        win32gui.EnumWindows(_enum, None)
        return {"success": True, "windows": windows}
    except Exception as e:
        return {"success": False, "error": str(e)}


def take_screenshot(region: dict | None = None) -> dict:
    """Capture a screenshot of the screen and save it to a temp file.

    Returns the file path instead of raw base64 to avoid overflowing the
    LLM context window with megabytes of image data.

    Args:
        region: Optional dict with keys top, left, width, height to capture a sub-region.
    """
    try:
        import mss
        from PIL import Image

        with mss.mss() as sct:
            mon = region or sct.monitors[1]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            # Save to a deterministic temp file (overwritten each capture)
            out_path = Path(tempfile.gettempdir()) / "wodi_screenshot.jpg"
            img.save(str(out_path), format="JPEG", quality=85)

        return {
            "success": True,
            "path": str(out_path),
            "size": list(img.size),
            "message": f"Screenshot saved to {out_path}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
