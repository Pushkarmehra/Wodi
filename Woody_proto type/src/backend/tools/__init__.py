"""
Nex Tools Package
All agent tools (web search, desktop automation, file management, system commands)
are centralized in this file.
"""
import os
import time
import subprocess
import pyautogui
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

# Configure PyAutoGUI safety settings
pyautogui.FAILSAFE = True  # Move mouse to top-left corner to emergency abort
pyautogui.PAUSE = 0.5     # Pause between PyAutoGUI actions


# ── 1. Web Search Tool ──

@tool
def web_search(query: str) -> str:
    """
    Performs a web search using Tavily API for the given query.
    
    Args:
        query: Search query string.
        
    Returns:
        String containing search results.
    """
    try:
        tavily = TavilySearch(max_results=3)
        res = tavily.invoke(query)
        if isinstance(res, dict) and "results" in res:
            formatted = []
            for item in res["results"]:
                snippet = item.get("content", "")[:350]
                formatted.append(f"Title: {item.get('title', '')}\nURL: {item.get('url', '')}\nSnippet: {snippet}")
            return "\n\n".join(formatted)
        return str(res)[:1200]
    except Exception as e:
        return f"Web search error: {str(e)}"


# ── 2. Desktop Automation Tools ──

@tool
def open_app(app_name: str, target: str = "") -> str:
    """
    Launches a desktop application (e.g., 'brave', 'chrome', 'notepad', 'calc', 'code')
    and optionally opens a specified URL or file path inside it (e.g. 'https://youtube.com').
    
    Args:
        app_name: Name of application to open (e.g., 'brave', 'chrome', 'notepad').
        target: Optional URL or file path to open in the app (e.g., 'https://youtube.com').
        
    Returns:
        Status message.
    """
    try:
        cmd = f'start {app_name} "{target}"' if target else f'start {app_name}'
        subprocess.Popen(cmd, shell=True)

        time.sleep(5.0)  # Allow window time to launch and focus
        target_msg = f" with target '{target}'" if target else ""
        return f"Successfully opened {app_name}{target_msg}."
    except Exception as e:
        return f"Failed to open application '{app_name}': {str(e)}"


@tool
def type_text(text: str, press_enter: bool = True) -> str:
    """
    Types text into the currently active/focused window.
    
    Args:
        text: The string text to type.
        press_enter: Whether to press Enter after typing.
        
    Returns:
        Status message.
    """
    try:
        pyautogui.write(text, interval=0.03)
        if press_enter:
            pyautogui.press("enter")
        return f"Typed text into active window: '{text}'"
    except Exception as e:
        return f"Failed to type text: {str(e)}"


@tool
def press_hotkey(shortcut: str) -> str:
    """
    Sends key combinations to the active window (e.g. 'ctrl,l', 'ctrl,t', 'enter', 'alt,f4').
    
    Args:
        shortcut: Comma-separated list of keys (e.g. 'ctrl,l' or 'enter').
        
    Returns:
        Status message.
    """
    try:
        keys = [k.strip().lower() for k in shortcut.split(",")]
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return f"Pressed hotkey: '{shortcut}'"
    except Exception as e:
        return f"Failed to press hotkey '{shortcut}': {str(e)}"


@tool
def click_screen(x: int, y: int, clicks: int = 1, button: str = "left") -> str:
    """
    Clicks at specific screen pixel coordinates (X, Y).
    
    Args:
        x: Horizontal screen pixel coordinate.
        y: Vertical screen pixel coordinate.
        clicks: Number of clicks (1 for single, 2 for double click).
        button: 'left', 'right', or 'middle'.
        
    Returns:
        Status message.
    """
    try:
        pyautogui.click(x=x, y=y, clicks=clicks, button=button)
        return f"Clicked {button} button at screen coordinates ({x}, {y})."
    except Exception as e:
        return f"Failed to click at ({x}, {y}): {str(e)}"


@tool
def take_screenshot(filename: str = "screen_capture.png") -> str:
    """
    Captures a full-screen screenshot and saves it to a file.
    
    Args:
        filename: File path to save the screenshot.
        
    Returns:
        Confirmation message with file location.
    """
    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(filename)
        width, height = screenshot.size
        return f"Screenshot saved: '{filename}' (Resolution: {width}x{height})"
    except Exception as e:
        return f"Failed to capture screenshot: {str(e)}"


# Centralized List of All Tools for LangGraph Binding
ALL_TOOLS = [
    web_search,
    open_app,
    type_text,
    press_hotkey,
    click_screen,
    take_screenshot,
]