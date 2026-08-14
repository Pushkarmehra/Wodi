"""
Telemetry — Anonymous local-only usage metrics. [Phase 5 Stub]

Wodi collects ZERO data externally. All telemetry is local only,
viewable by the user in the Activity Panel, and opt-out by default.

Phase 5 will add:
  - Local Prometheus metrics server (accessible at localhost:9090)
  - Latency histograms per agent/action
  - Error rate tracking
  - Model token usage tracking
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from wodi.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class LatencySample:
    action: str
    agent: str
    latency_ms: float
    success: bool
    timestamp: float = field(default_factory=time.time)


class Telemetry:
    """
    Local-only telemetry collector.

    Privacy guarantee: No data ever leaves the machine.
    All metrics stored in memory only (cleared on restart).
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._samples: list[LatencySample] = []
        self._error_counts: dict[str, int] = defaultdict(int)
        self._request_count: int = 0
        self._token_count: int = 0
        self._start_time = time.time()

    def record_action(
        self,
        action: str,
        agent: str,
        latency_ms: float,
        success: bool,
    ) -> None:
        if not self._enabled:
            return
        self._samples.append(LatencySample(action, agent, latency_ms, success))
        if not success:
            self._error_counts[f"{agent}.{action}"] += 1
        self._request_count += 1
        # Keep last 1000 samples
        if len(self._samples) > 1000:
            self._samples = self._samples[-1000:]

    def record_tokens(self, count: int) -> None:
        if self._enabled:
            self._token_count += count

    def get_summary(self) -> dict:
        """Return a summary of all local metrics."""
        if not self._samples:
            return {"requests": 0, "uptime_minutes": round((time.time() - self._start_time) / 60, 1)}

        latencies = [s.latency_ms for s in self._samples]
        successes = [s for s in self._samples if s.success]
        return {
            "requests": self._request_count,
            "success_rate": round(len(successes) / len(self._samples) * 100, 1),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
            "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1),
            "tokens_used": self._token_count,
            "uptime_minutes": round((time.time() - self._start_time) / 60, 1),
            "top_errors": dict(sorted(self._error_counts.items(), key=lambda x: -x[1])[:5]),
        }

    def reset(self) -> None:
        self._samples.clear()
        self._error_counts.clear()
        self._request_count = 0
        self._token_count = 0
