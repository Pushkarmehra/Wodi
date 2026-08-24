"""
Built-in System Tools — MCP tool server functions for system information.
"""
from __future__ import annotations

import datetime
import os
import platform

import psutil

# Ordered list for deterministic schema registration
TOOLS = [
    "get_time_date",
    "get_system_stats",
    "list_processes",
    "get_clipboard",
    "set_clipboard",
    "get_battery",
    "get_network_info",
    "run_command",
]


def get_time_date() -> dict:
    """Get the current local time, date, and timezone.

    Returns a dict with keys: success, time, date, iso, timezone.
    """
    now = datetime.datetime.now().astimezone()
    return {
        "success": True,
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "iso": now.isoformat(),
        "timezone": str(now.tzname()),
    }


def get_system_stats() -> dict:
    """Get current CPU usage, RAM usage, and disk usage statistics.

    Returns a dict with cpu_percent, ram_percent, ram_used_gb, ram_total_gb,
    disk_percent, disk_free_gb, and platform string.
    """
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()

    # On Windows, '/' resolves to the system drive root (C:\\).
    # Use the drive of the current working directory to be safe on all platforms.
    disk_root = os.path.abspath(os.sep)
    try:
        disk = psutil.disk_usage(disk_root)
        disk_percent = disk.percent
        disk_free_gb = round(disk.free / 1e9, 2)
    except Exception:
        disk_percent = None
        disk_free_gb = None

    return {
        "success": True,
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / 1e9, 2),
        "ram_total_gb": round(mem.total / 1e9, 2),
        "disk_percent": disk_percent,
        "disk_free_gb": disk_free_gb,
        "platform": platform.platform(),
    }


def list_processes(top_n: int = 10, sort_by: str = "cpu") -> dict:
    """List the top running processes sorted by CPU or memory usage.

    Args:
        top_n: Number of processes to return (default 10).
        sort_by: Sort key — 'cpu' for CPU percent or 'memory' for RAM percent.
    """
    procs: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    procs.sort(key=lambda x: x.get(key) or 0, reverse=True)
    return {"success": True, "processes": procs[:top_n]}


def get_clipboard() -> dict:
    """Get the current text content of the Windows clipboard.

    Returns a dict with keys: success, clipboard (the text), or error.
    Note: the result key is 'clipboard' to match the kernel fast-path formatter.
    """
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return {"success": True, "clipboard": text, "text": text}
        finally:
            win32clipboard.CloseClipboard()
        return {"success": True, "clipboard": "", "text": ""}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_battery() -> dict:
    """Get the current battery status including percentage, charging state, and time remaining.

    Returns a dict with percent, plugged_in, time_left_minutes, or a note if no battery.
    """
    batt = psutil.sensors_battery()
    if batt:
        return {
            "success": True,
            "percent": round(batt.percent, 1),
            "plugged_in": batt.power_plugged,
            "time_left_minutes": (
                round(batt.secsleft / 60) if batt.secsleft > 0 else None
            ),
        }
    return {"success": True, "percent": None, "note": "No battery detected (desktop system)."}


def set_clipboard(text: str) -> dict:
    """Set the current text content of the Windows clipboard.

    Args:
        text: The string to place into the clipboard.
    """
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        return {"success": True, "message": f"Copied {len(text)} characters to clipboard."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_command(command: str, timeout_seconds: int = 15) -> dict:
    """Execute a safe shell/PowerShell command on Windows and return its standard output.

    Args:
        command: The command line string to run (e.g. 'dir', 'ipconfig', 'echo hello').
        timeout_seconds: Maximum time to wait for execution (default 15s).
    """
    import subprocess

    try:
        # Block overtly destructive commands
        dangerous = ["format ", "rmdir /s /q c:", "del /f /s /q c:\\windows", "drop database"]
        if any(d in command.lower() for d in dangerous):
            return {"success": False, "error": "Command blocked for safety reasons."}

        res = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "success": res.returncode == 0,
            "returncode": res.returncode,
            "return_code": res.returncode,
            "stdout": res.stdout[:2000],
            "output": res.stdout[:2000],
            "stderr": res.stderr[:1000],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout_seconds} seconds."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_network_info() -> dict:
    """Get network interface addresses and aggregate I/O counters in megabytes.

    Returns a dict with interfaces (name → address list) and bytes_sent_mb / bytes_recv_mb.
    """
    try:
        ifaces = psutil.net_if_addrs()
        stats = psutil.net_io_counters()
        return {
            "success": True,
            "interfaces": {
                name: [a.address for a in addrs] for name, addrs in ifaces.items()
            },
            "bytes_sent_mb": round(stats.bytes_sent / 1e6, 2),
            "bytes_recv_mb": round(stats.bytes_recv / 1e6, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

