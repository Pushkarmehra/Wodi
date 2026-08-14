"""
Sandbox — Windows Job Object subprocess isolation. [Phase 3 Stub]
"""
from __future__ import annotations
from wodi.utils.logging import get_logger
log = get_logger(__name__)


class JobObjectSandbox:
    """Windows Job Object sandbox for untrusted subprocess execution. Phase 3."""
    def run(self, command: list[str], timeout_seconds: int = 30) -> dict:
        # TODO (Phase 3): Implement Windows Job Object with CPU/memory limits
        log.warning("sandbox.not_implemented", phase="Phase 3")
        return {"success": False, "error": "Sandbox not yet implemented"}
