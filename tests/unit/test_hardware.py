"""Unit tests for hardware detection."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from wodi.utils.hardware import detect_hardware, HardwareTier, _assign_tier


class TestHardwareTierAssignment:
    def test_lite_cpu_only(self):
        tier = _assign_tier(ram_gb=8.0, vram_gb=0.0, has_gpu=False)
        assert tier == HardwareTier.LITE

    def test_standard_ram_only(self):
        tier = _assign_tier(ram_gb=16.0, vram_gb=0.0, has_gpu=False)
        assert tier == HardwareTier.STANDARD

    def test_standard_entry_gpu(self):
        tier = _assign_tier(ram_gb=8.0, vram_gb=4.0, has_gpu=True)
        assert tier == HardwareTier.STANDARD

    def test_pro_discrete_gpu(self):
        tier = _assign_tier(ram_gb=32.0, vram_gb=8.0, has_gpu=True)
        assert tier == HardwareTier.PRO

    def test_pro_high_vram(self):
        tier = _assign_tier(ram_gb=16.0, vram_gb=12.0, has_gpu=True)
        assert tier == HardwareTier.PRO

    def test_lite_insufficient_ram(self):
        tier = _assign_tier(ram_gb=6.0, vram_gb=0.0, has_gpu=False)
        assert tier == HardwareTier.LITE
