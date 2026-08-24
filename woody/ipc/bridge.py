"""
IPC Bridge — Kernel ↔ UI communication stubs. [Phase 5]

In Phase 5, the kernel and UI will optionally run as separate processes,
communicating via gRPC (defined in Woody.proto) for:
  - Lower UI crash impact on kernel stability
  - Remote kernel control (phone/browser)
  - Multi-session support

For now (Phase 0–2), the kernel and UI share the same process
via Qt signals (see Woody/ui/app.py KernelSignalBridge).
"""
from __future__ import annotations

from woody.utils.logging import get_logger

log = get_logger(__name__)


class IPCBridge:
    """
    Stub for the kernel↔UI IPC channel.

    Phase 5: Replace Qt signal bridge in Woody/ui/app.py
    with this gRPC-backed bridge.
    """

    def __init__(self, mode: str = "inprocess") -> None:
        self.mode = mode  # inprocess | grpc
        log.debug("ipc.bridge_created", mode=mode)

    async def send(self, event: str, payload: dict) -> None:
        """Send an event from kernel to UI."""
        if self.mode == "inprocess":
            # Direct call — no serialization needed
            return
        # TODO (Phase 5): Serialize and send via gRPC channel
        log.warning("ipc.grpc_not_implemented", phase="Phase 5")

    async def receive(self) -> tuple[str, dict]:
        """Receive an event from UI."""
        # TODO (Phase 5): gRPC stream receive
        raise NotImplementedError("IPC gRPC bridge not yet implemented")
