"""
Built-in System Tools — MCP tool server functions for system information.
"""
from __future__ import annotations

import datetime
import platform

import psutil

TOOLS = {
    "get_time_date",
    "get_system_stats",
    "list_processes",
    "get_clipboard",
    "get_battery",
    "get_network_info",
}


def get_time_date() -> dict:
    now = datetime.datetime.now()
    return {
        "success": True,
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "iso": now.isoformat(),
        "timezone": str(datetime.datetime.now().astimezone().tzname()),
    }


def get_system_stats() -> dict:
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "success": True,
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / 1e9, 2),
        "ram_total_gb": round(mem.total / 1e9, 2),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / 1e9, 2),
        "platform": platform.platform(),
    }


def list_processes(top_n: int = 10, sort_by: str = "cpu") -> dict:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    procs.sort(key=lambda x: x.get(key, 0) or 0, reverse=True)
    return {"success": True, "processes": procs[:top_n]}


def get_clipboard() -> dict:
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return {"success": True, "text": text}
        finally:
            win32clipboard.CloseClipboard()
        return {"success": True, "text": ""}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_battery() -> dict:
    batt = psutil.sensors_battery()
    if batt:
        return {
            "success": True,
            "percent": batt.percent,
            "plugged_in": batt.power_plugged,
            "time_left_minutes": round(batt.secsleft / 60) if batt.secsleft > 0 else None,
        }
    return {"success": True, "percent": None, "note": "No battery"}


def get_network_info() -> dict:
    try:
        ifaces = psutil.net_if_addrs()
        stats = psutil.net_io_counters()
        return {
            "success": True,
            "interfaces": {n: [a.address for a in addrs] for n, addrs in ifaces.items()},
            "bytes_sent_mb": round(stats.bytes_sent / 1e6, 2),
            "bytes_recv_mb": round(stats.bytes_recv / 1e6, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
