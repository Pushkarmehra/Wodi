"""
MCP Plugin Manifest — loads and validates MCP plugin manifests.

Enforces the permission tier model:
  - read_only        : auto-allowed (screen OCR, file read, system stats)
  - user_confirm     : shows inline confirmation card before executing
  - privileged       : requires explicit per-session opt-in
  - denied           : blocked regardless (registry edits, UAC actions)

Each plugin ships a manifest.json specifying its tools and permission tier.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from wodi.utils.logging import get_logger

log = get_logger(__name__)


class PermissionTier(str, Enum):
    READ_ONLY = "read_only"
    USER_CONFIRM = "user_confirm"
    PRIVILEGED = "privileged"
    DENIED = "denied"


@dataclass
class PluginManifest:
    name: str
    version: str
    transport: str          # "stdio" | "http"
    permission_tier: PermissionTier
    tools: list[str]
    sandbox: str            # "process_isolated" | "job_object" | "wsl2" | "none"
    entrypoint: str = ""    # Path to server script (stdio) or URL (http)
    description: str = ""


class PermissionDeniedError(Exception):
    pass


class ManifestLoader:
    """
    Discovers and validates MCP plugin manifests from a plugin directory.

    Usage:
        loader = ManifestLoader(plugin_dir="plugins")
        manifests = loader.discover()
        loader.check_permission(manifest, tool_name, tools_config)
    """

    def __init__(self, plugin_dir: str | Path = "plugins") -> None:
        self._plugin_dir = Path(plugin_dir)
        self._manifests: dict[str, PluginManifest] = {}

    def discover(self) -> list[PluginManifest]:
        """Scan plugin directory for manifest.json files."""
        if not self._plugin_dir.exists():
            log.debug("manifests.plugin_dir_missing", path=str(self._plugin_dir))
            return []

        found: list[PluginManifest] = []
        for manifest_path in self._plugin_dir.rglob("manifest.json"):
            m = self._load_manifest(manifest_path)
            if m:
                self._manifests[m.name] = m
                found.append(m)
                log.info("manifests.loaded", plugin=m.name, tools=len(m.tools), tier=m.permission_tier)

        log.info("manifests.discovery_complete", total=len(found))
        return found

    def _load_manifest(self, path: Path) -> PluginManifest | None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            tier_str = data.get("permission_tier", "user_confirm")
            try:
                tier = PermissionTier(tier_str)
            except ValueError:
                tier = PermissionTier.USER_CONFIRM

            return PluginManifest(
                name=data["name"],
                version=data.get("version", "0.0.1"),
                transport=data.get("transport", "stdio"),
                permission_tier=tier,
                tools=data.get("tools", []),
                sandbox=data.get("sandbox", "process_isolated"),
                entrypoint=str(path.parent / data.get("entrypoint", "server.py")),
                description=data.get("description", ""),
            )
        except Exception as e:
            log.warning("manifests.load_error", path=str(path), error=str(e))
            return None

    def check_permission(
        self,
        manifest: PluginManifest,
        tool_name: str,
        auto_allow_read: bool = True,
        auto_allow_system_info: bool = True,
        block_registry_edits: bool = True,
    ) -> PermissionTier:
        """
        Determine the effective permission tier for a tool call.
        Raises PermissionDeniedError for DENIED tier.
        Returns the effective tier for the caller to handle (confirm/proceed).
        """
        # Tool must be declared in the manifest
        if tool_name not in manifest.tools:
            raise PermissionDeniedError(
                f"Tool '{tool_name}' not declared in manifest '{manifest.name}'"
            )

        tier = manifest.permission_tier

        # Apply config overrides
        if block_registry_edits and "registry" in tool_name.lower():
            raise PermissionDeniedError("Registry edits are blocked by default")

        if tier == PermissionTier.DENIED:
            raise PermissionDeniedError(
                f"Tool '{tool_name}' from plugin '{manifest.name}' is in DENIED tier"
            )

        # Auto-allow read-only and system-info if configured
        if tier == PermissionTier.READ_ONLY and auto_allow_read:
            return tier
        if auto_allow_system_info and any(
            kw in tool_name for kw in ("system_stats", "get_time", "list_process", "get_clipboard")
        ):
            return PermissionTier.READ_ONLY

        return tier

    def get_manifest(self, plugin_name: str) -> PluginManifest | None:
        return self._manifests.get(plugin_name)

    def get_all_tools(self) -> dict[str, PluginManifest]:
        """Return a mapping of tool_name → manifest for all loaded plugins."""
        result: dict[str, PluginManifest] = {}
        for manifest in self._manifests.values():
            for tool in manifest.tools:
                result[tool] = manifest
        return result
