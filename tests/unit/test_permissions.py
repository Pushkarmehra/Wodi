"""Unit tests for MCP manifest permission enforcement."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from wodi.tools.mcp_manifest import ManifestLoader, PermissionDeniedError, PermissionTier


class TestManifestPermissions:
    def _make_manifest(self, tmp_path: Path, tier: str, tools: list[str]) -> ManifestLoader:
        plugin_dir = tmp_path / "plugins" / "test_plugin"
        plugin_dir.mkdir(parents=True)
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "transport": "stdio",
            "permission_tier": tier,
            "tools": tools,
            "sandbox": "process_isolated",
        }
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
        loader = ManifestLoader(plugin_dir=tmp_path / "plugins")
        loader.discover()
        return loader

    def test_read_only_auto_allowed(self, tmp_path: Path):
        loader = self._make_manifest(tmp_path, "read_only", ["get_system_stats"])
        m = loader.get_manifest("test-plugin")
        tier = loader.check_permission(m, "get_system_stats", auto_allow_read=True)
        assert tier == PermissionTier.READ_ONLY

    def test_undeclared_tool_denied(self, tmp_path: Path):
        loader = self._make_manifest(tmp_path, "user_confirm", ["get_system_stats"])
        m = loader.get_manifest("test-plugin")
        with pytest.raises(PermissionDeniedError):
            loader.check_permission(m, "delete_files", auto_allow_read=True)

    def test_denied_tier_always_raises(self, tmp_path: Path):
        loader = self._make_manifest(tmp_path, "denied", ["dangerous_tool"])
        m = loader.get_manifest("test-plugin")
        with pytest.raises(PermissionDeniedError):
            loader.check_permission(m, "dangerous_tool")

    def test_registry_blocked(self, tmp_path: Path):
        loader = self._make_manifest(tmp_path, "privileged", ["edit_registry"])
        m = loader.get_manifest("test-plugin")
        with pytest.raises(PermissionDeniedError, match="Registry"):
            loader.check_permission(m, "edit_registry", block_registry_edits=True)

    def test_user_confirm_returned(self, tmp_path: Path):
        loader = self._make_manifest(tmp_path, "user_confirm", ["send_email"])
        m = loader.get_manifest("test-plugin")
        tier = loader.check_permission(m, "send_email", auto_allow_read=False)
        assert tier == PermissionTier.USER_CONFIRM
