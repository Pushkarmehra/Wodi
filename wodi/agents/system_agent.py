"""
System Agent — psutil/pywin32 system information and control.
"""
from __future__ import annotations

import datetime
import platform
from typing import Any

import psutil

from wodi.agents.base_agent import AgentResult, BaseAgent
from wodi.utils.logging import get_logger

log = get_logger(__name__)


class SystemAgent(BaseAgent):
    AGENT_NAME = "system_agent"
    ALLOWED_ACTIONS = {
        "get_time_date",
        "get_system_stats",
        "list_processes",
        "kill_process",
        "get_clipboard",
        "set_clipboard",
        "get_battery",
        "get_network_info",
        "clarify",
    }

    def __init__(self, confirm_callback: Any | None = None) -> None:
        super().__init__(max_retries=1, confirm_callback=confirm_callback)

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        handlers = {
            "get_time_date": self._get_time_date,
            "get_system_stats": self._get_system_stats,
            "list_processes": self._list_processes,
            "kill_process": self._kill_process,
            "get_clipboard": self._get_clipboard,
            "set_clipboard": self._set_clipboard,
            "get_battery": self._get_battery,
            "get_network_info": self._get_network_info,
            "clarify": self._clarify,
        }
        handler = handlers.get(action)
        if not handler:
            return AgentResult(success=False, output=None, error=f"Unknown action: {action}")
        return await handler(params, context)

    async def _get_time_date(self, params: dict, context: dict) -> AgentResult:
        now = datetime.datetime.now()
        return AgentResult(success=True, output={
            "time": now.strftime("%I:%M %p"),
            "date": now.strftime("%A, %B %d, %Y"),
            "timestamp": now.isoformat(),
            "timezone": str(datetime.datetime.now().astimezone().tzname()),
        })

    async def _get_system_stats(self, params: dict, context: dict) -> AgentResult:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return AgentResult(success=True, output={
            "cpu_percent": cpu,
            "ram_used_gb": round(mem.used / 1e9, 2),
            "ram_total_gb": round(mem.total / 1e9, 2),
            "ram_percent": mem.percent,
            "disk_used_gb": round(disk.used / 1e9, 2),
            "disk_total_gb": round(disk.total / 1e9, 2),
            "disk_percent": disk.percent,
            "platform": platform.platform(),
        })

    async def _list_processes(self, params: dict, context: dict) -> AgentResult:
        top_n = params.get("top_n", 10)
        sort_by = params.get("sort_by", "cpu")  # cpu | memory
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
        procs.sort(key=lambda x: x.get(key, 0), reverse=True)
        return AgentResult(success=True, output=procs[:top_n])

    async def _kill_process(self, params: dict, context: dict) -> AgentResult:
        # Requires user confirmation — call confirm_callback
        pid = params.get("pid")
        name = params.get("name", "")
        confirmed = await self._request_confirmation("kill_process", params)
        if not confirmed:
            return AgentResult(success=False, output=None, error="User denied kill_process")
        try:
            if pid:
                psutil.Process(int(pid)).terminate()
                return AgentResult(success=True, output=f"Killed PID {pid}")
            for p in psutil.process_iter(["pid", "name"]):
                if name.lower() in p.info["name"].lower():
                    p.terminate()
                    return AgentResult(success=True, output=f"Killed {p.info['name']} (PID {p.info['pid']})")
            return AgentResult(success=False, output=None, error=f"Process '{name}' not found")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _get_clipboard(self, params: dict, context: dict) -> AgentResult:
        from wodi.perception.clipboard import ClipboardWatcher
        watcher = ClipboardWatcher()
        content = watcher._read_clipboard()
        return AgentResult(success=True, output={"clipboard": content})

    async def _set_clipboard(self, params: dict, context: dict) -> AgentResult:
        text = params.get("text", "")
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return AgentResult(success=True, output=f"Clipboard set ({len(text)} chars)")
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e))

    async def _get_battery(self, params: dict, context: dict) -> AgentResult:
        batt = psutil.sensors_battery()
        if batt:
            return AgentResult(success=True, output={
                "percent": batt.percent,
                "plugged_in": batt.power_plugged,
                "time_left_minutes": round(batt.secsleft / 60) if batt.secsleft > 0 else None,
            })
        return AgentResult(success=True, output={"percent": None, "note": "No battery detected"})

    async def _get_network_info(self, params: dict, context: dict) -> AgentResult:
        ifaces = psutil.net_if_addrs()
        stats = psutil.net_io_counters()
        return AgentResult(success=True, output={
            "interfaces": {name: [a.address for a in addrs] for name, addrs in ifaces.items()},
            "bytes_sent_mb": round(stats.bytes_sent / 1e6, 2),
            "bytes_recv_mb": round(stats.bytes_recv / 1e6, 2),
        })

    async def _clarify(self, params: dict, context: dict) -> AgentResult:
        return AgentResult(success=True, output={"clarification_needed": True,
                                                  "message": params.get("message", "Please clarify.")})
