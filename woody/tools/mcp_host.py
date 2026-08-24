"""
MCP Host — orchestrates tool discovery, permission checking, and invocation.

The host:
  1. Discovers all MCP plugin manifests at startup
  2. Provides a tool list to each agent (scoped by agent type)
  3. Dispatches tool calls with permission checking
  4. Handles user-confirm tier via the confirmation callback
  5. Logs every tool call to the audit log
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from woody.tools.mcp_manifest import ManifestLoader, PermissionDeniedError, PermissionTier, PluginManifest
from woody.utils.logging import get_logger

log = get_logger(__name__)


class MCPHost:
    """
    Central MCP host that manages all tool plugins for Woody.

    Usage:
        host = MCPHost(plugin_dir="plugins", confirm_callback=my_confirm_fn)
        host.start()
        result = await host.invoke("Woody-system-tools", "get_time_date", {})
    """

    def __init__(
        self,
        plugin_dir: str = "plugins",
        confirm_callback: Callable[[str, str, dict], Any] | None = None,
        audit_log: Any | None = None,
        tools_config: Any | None = None,
    ) -> None:
        self._plugin_dir = plugin_dir
        self._confirm_callback = confirm_callback
        self._audit_log = audit_log
        self._tools_config = tools_config
        self._loader = ManifestLoader(plugin_dir=plugin_dir)
        self._manifests: list[PluginManifest] = []
        self._tool_map: dict[str, PluginManifest] = {}
        self._servers: dict[str, Any] = {}   # plugin_name → running server process

    def start(self) -> None:
        """Discover all plugins and build the tool map."""
        self._manifests = self._loader.discover()
        self._tool_map = self._loader.get_all_tools()
        log.info(
            "mcp_host.ready",
            plugins=len(self._manifests),
            tools=len(self._tool_map),
        )

    def get_tool_list(self, agent_name: str | None = None) -> list[dict]:
        """
        Return the OpenAI-compatible tool schema list for an agent.
        Optionally filtered by agent_name (future: per-agent scoping).
        """
        # For now returns all tools — per-agent scoping in Phase 3
        tools = []
        for tool_name, manifest in self._tool_map.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": f"[{manifest.permission_tier.value}] From plugin: {manifest.name}",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                }
            })
        return tools

    async def invoke(
        self,
        plugin_name: str,
        tool_name: str,
        arguments: dict,
        agent_name: str = "unknown",
    ) -> Any:
        """
        Invoke a tool with full permission checking and audit logging.
        """
        manifest = self._loader.get_manifest(plugin_name)
        if not manifest:
            raise ValueError(f"Plugin '{plugin_name}' not found")

        # Permission check
        cfg = self._tools_config
        try:
            effective_tier = self._loader.check_permission(
                manifest=manifest,
                tool_name=tool_name,
                auto_allow_read=cfg.auto_allow_read if cfg else True,
                auto_allow_system_info=cfg.auto_allow_system_info if cfg else True,
                block_registry_edits=cfg.block_registry_edits if cfg else True,
            )
        except PermissionDeniedError as e:
            log.warning("mcp_host.permission_denied", tool=tool_name, reason=str(e))
            self._audit(plugin_name, tool_name, arguments, None, denied=True, reason=str(e))
            raise

        # User confirmation for user_confirm tier
        confirmed: bool | None = None
        if effective_tier == PermissionTier.USER_CONFIRM:
            confirmed = await self._get_confirmation(tool_name, arguments)
            if not confirmed:
                self._audit(plugin_name, tool_name, arguments, None, confirmed=False)
                raise PermissionDeniedError(f"User denied '{tool_name}'")

        # Invoke the tool
        log.info("mcp_host.invoke", plugin=plugin_name, tool=tool_name, tier=effective_tier)
        try:
            result = await self._dispatch(plugin_name, tool_name, arguments)
            self._audit(plugin_name, tool_name, arguments, result, confirmed=confirmed)
            return result
        except Exception as e:
            self._audit(plugin_name, tool_name, arguments, None, error=str(e))
            raise

    async def _dispatch(self, plugin_name: str, tool_name: str, arguments: dict) -> Any:
        """Dispatch to the appropriate built-in or external MCP server."""
        # Built-in tool dispatch
        from woody.tools.builtin import desktop_tools, system_tools
        builtin_map = {
            **{t: desktop_tools for t in desktop_tools.TOOLS},
            **{t: system_tools for t in system_tools.TOOLS},
        }
        module = builtin_map.get(tool_name)
        if module:
            handler = getattr(module, tool_name, None)
            if handler:
                if asyncio.iscoroutinefunction(handler):
                    return await handler(**arguments)
                else:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, lambda: handler(**arguments))

        raise NotImplementedError(f"Tool '{tool_name}' dispatcher not found")

    async def _get_confirmation(self, tool_name: str, arguments: dict) -> bool:
        if self._confirm_callback is None:
            log.warning("mcp_host.no_confirm_callback", tool=tool_name, default="deny")
            return False
        try:
            result = self._confirm_callback(tool_name, arguments)
            if asyncio.iscoroutine(result):
                return await result
            return bool(result)
        except Exception as e:
            log.error("mcp_host.confirm_error", error=str(e))
            return False

    def _audit(
        self,
        plugin: str,
        tool: str,
        inputs: dict,
        output: Any,
        confirmed: bool | None = None,
        denied: bool = False,
        error: str | None = None,
        reason: str | None = None,
    ) -> None:
        if self._audit_log:
            import time
            self._audit_log.log_entry({
                "plugin": plugin,
                "tool": tool,
                "inputs": inputs,
                "output": str(output)[:500] if output else None,
                "confirmed": confirmed,
                "denied": denied,
                "error": error,
                "reason": reason,
                "timestamp": time.time(),
            })

    def stop(self) -> None:
        """Shutdown all running plugin server processes."""
        for name, proc in self._servers.items():
            try:
                proc.terminate()
                log.info("mcp_host.plugin_stopped", plugin=name)
            except Exception:
                pass
        self._servers.clear()
