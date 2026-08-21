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

# Expanded common application aliases
APP_ALIASES: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "brave": "brave.exe",
    "brave browser": "brave.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "vscode": "code.exe",
    "code": "code.exe",
    "visual studio code": "code.exe",
    "cursor": "cursor.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "paint": "mspaint.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "notepad++": "notepad++.exe",
    "spotify": "spotify.exe",
    "vlc": "vlc.exe",
    "discord": "discord.exe",
    "slack": "slack.exe",
    "teams": "ms-teams.exe",
    "telegram": "telegram.exe",
    "whatsapp": "whatsapp.exe",
    "steam": "steam.exe",
    "obs": "obs64.exe",
    "obsidian": "obsidian.exe",
    "settings": "ms-settings:",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
}


def find_windows_app(app_name: str) -> str | None:
    """Dynamically search Windows Registry and Start Menu for installed apps."""
    clean_name = app_name.lower().strip()
    target_exe = APP_ALIASES.get(clean_name, f"{clean_name}.exe")

    # 1. Check Windows Registry App Paths (HKLM & HKCU)
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                key = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths")
                for i in range(winreg.QueryInfoKey(key)[0]):
                    subkey_name = winreg.EnumKey(key, i)
                    subkey_lower = subkey_name.lower()
                    if clean_name == subkey_lower.removesuffix(".exe") or clean_name in subkey_lower:
                        sub = winreg.OpenKey(key, subkey_name)
                        val, _ = winreg.QueryValueEx(sub, "")
                        if val and os.path.exists(val):
                            return val
            except Exception:
                pass
    except Exception:
        pass

    # 2. Check Windows Start Menu shortcuts (.lnk)
    try:
        import glob
        search_dirs = [
            os.environ.get("APPDATA", "") + r"\Microsoft\Windows\Start Menu\Programs",
            os.environ.get("PROGRAMDATA", "") + r"\Microsoft\Windows\Start Menu\Programs",
            os.environ.get("LOCALAPPDATA", "") + r"\Programs",
        ]
        for base in search_dirs:
            if not base or not os.path.exists(base):
                continue
            for lnk in glob.glob(base + r"\**\*.lnk", recursive=True):
                lnk_name = os.path.splitext(os.path.basename(lnk))[0].lower()
                if clean_name in lnk_name or lnk_name in clean_name:
                    return lnk
    except Exception:
        pass

    # 3. Check system PATH via 'where'
    try:
        res = subprocess.run(["where", target_exe], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            if lines:
                return lines[0]
    except Exception:
        pass

    return None


def open_app(app_name: str) -> dict:
    """Open an application by name on Windows.

    Args:
        app_name: Name of the application to open (e.g. 'brave', 'chrome', 'notepad', 'calculator').
    """
    clean_name = app_name.lower().strip()
    if clean_name == "settings" or clean_name.startswith("ms-settings:"):
        os.startfile("ms-settings:")
        return {"success": True, "message": "Opened Windows Settings."}

    # 1. Try dynamic locator
    resolved_path = find_windows_app(clean_name)
    if resolved_path:
        try:
            os.startfile(resolved_path)
            return {"success": True, "message": f"Opened {app_name}."}
        except Exception as e:
            try:
                subprocess.Popen([resolved_path], shell=False)
                return {"success": True, "message": f"Opened {app_name}."}
            except Exception as e2:
                return {"success": False, "error": f"Failed to launch {resolved_path}: {e2}"}

    # 2. Try alias or direct execution
    exe = APP_ALIASES.get(clean_name, clean_name)
    try:
        os.startfile(exe)
        return {"success": True, "message": f"Opened {app_name} ({exe})."}
    except Exception:
        try:
            subprocess.Popen(f'start "" "{exe}"', shell=True)
            return {"success": True, "message": f"Opened {app_name}."}
        except Exception as e:
            return {
                "success": False,
                "error": f"Could not find or open application '{app_name}'. Error: {e}",
            }



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
