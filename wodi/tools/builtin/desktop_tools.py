"""
Built-in Desktop Tools — MCP tool server functions for desktop automation.
These are called directly by the MCP host dispatcher.
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Any

TOOLS = {
    "open_app",
    "close_app",
    "focus_window",
    "type_text",
    "press_key",
    "get_open_windows",
    "take_screenshot",
}

APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "explorer": "explorer.exe",
    "vscode": "code.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "paint": "mspaint.exe",
    "notepad++": "notepad++.exe",
}


def open_app(app_name: str) -> dict:
    exe = APP_ALIASES.get(app_name.lower().strip(), app_name)
    try:
        subprocess.Popen(exe, shell=True)
        time.sleep(1)
        return {"success": True, "message": f"Opened {app_name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def close_app(app_name: str) -> dict:
    exe = APP_ALIASES.get(app_name.lower().strip(), app_name).replace(".exe", "")
    try:
        import psutil
        killed = []
        for p in psutil.process_iter(["name", "pid"]):
            if exe.lower() in p.info["name"].lower():
                p.terminate()
                killed.append(p.info["name"])
        return {"success": bool(killed), "closed": killed}
    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_window(title: str) -> dict:
    try:
        import win32gui, win32con
        hwnd = win32gui.FindWindow(None, title)
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return {"success": True, "hwnd": hwnd}
        return {"success": False, "error": f"Window '{title}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_text(text: str, interval: float = 0.03) -> dict:
    try:
        import pyautogui
        pyautogui.typewrite(text, interval=interval)
        return {"success": True, "chars": len(text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_key(key: str) -> dict:
    try:
        import pyautogui
        pyautogui.press(key)
        return {"success": True, "key": key}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_open_windows() -> dict:
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
    try:
        import mss
        from PIL import Image
        import io, base64
        with mss.mss() as sct:
            mon = region or sct.monitors[1]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return {
                "success": True,
                "base64": base64.b64encode(buf.getvalue()).decode(),
                "size": img.size,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
