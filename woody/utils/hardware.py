"""
Hardware detection and tier routing for Woody.

Detects GPU VRAM, system RAM, and CPU to assign the correct model tier.
Returns a WoodyTier enum used by kernel/config.py to load the right model YAML.

Tiers:
  - Lite     : CPU-only or <8GB RAM
  - Standard : 16GB RAM, integrated/entry GPU
  - Pro      : Discrete GPU ≥8GB VRAM
"""
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from enum import Enum

import psutil

from woody.utils.logging import get_logger

log = get_logger(__name__)


class HardwareTier(str, Enum):
    LITE = "lite"
    STANDARD = "standard"
    PRO = "pro"


@dataclass(frozen=True)
class HardwareProfile:
    tier: HardwareTier
    ram_gb: float
    gpu_name: str | None
    vram_gb: float
    cpu_cores: int
    has_cuda: bool
    has_rocm: bool
    platform: str


def detect_hardware() -> HardwareProfile:
    """Detect system hardware and return a HardwareProfile with tier assignment."""
    ram_gb = _get_ram_gb()
    gpu_name, vram_gb, has_cuda, has_rocm = _get_gpu_info()
    cpu_cores = psutil.cpu_count(logical=False) or 1

    tier = _assign_tier(ram_gb=ram_gb, vram_gb=vram_gb, has_gpu=(gpu_name is not None))

    profile = HardwareProfile(
        tier=tier,
        ram_gb=ram_gb,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        cpu_cores=cpu_cores,
        has_cuda=has_cuda,
        has_rocm=has_rocm,
        platform=platform.system(),
    )

    log.info(
        "hardware.detected",
        tier=tier.value,
        ram_gb=f"{ram_gb:.1f}",
        gpu=gpu_name or "none",
        vram_gb=f"{vram_gb:.1f}",
        cpu_cores=cpu_cores,
    )
    return profile


def _get_ram_gb() -> float:
    try:
        return psutil.virtual_memory().total / (1024**3)
    except Exception:
        return 8.0


def _get_gpu_info() -> tuple[str | None, float, bool, bool]:
    """Return (gpu_name, vram_gb, has_cuda, has_rocm)."""
    # Try nvidia-smi first (CUDA GPUs)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            # Take the GPU with the most VRAM if multiple
            best_name, best_vram = None, 0.0
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    try:
                        vram_mb = float(parts[1].strip())
                        vram_gb = vram_mb / 1024
                    except ValueError:
                        vram_gb = 0.0
                    if vram_gb > best_vram:
                        best_vram = vram_gb
                        best_name = name
            if best_name:
                return best_name, best_vram, True, False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Try ROCm / AMD
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json
            data = json.loads(result.stdout)
            # Simplified: just flag ROCm presence
            return "AMD GPU (ROCm)", 8.0, False, True
    except Exception:
        pass

    # Try wmic for Windows GPU name (no VRAM info, fallback)
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name,AdapterRAM", "/format:csv"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.strip().split(",")
                if len(parts) >= 3 and parts[1].strip().isdigit():
                    name = parts[2].strip()
                    vram_bytes = int(parts[1].strip())
                    vram_gb = vram_bytes / (1024**3)
                    if name and vram_gb > 0.5:
                        return name, vram_gb, False, False
    except Exception:
        pass

    return None, 0.0, False, False


def _assign_tier(ram_gb: float, vram_gb: float, has_gpu: bool) -> HardwareTier:
    """Assign hardware tier based on detected resources."""
    # Pro: discrete GPU with ≥8GB VRAM
    if has_gpu and vram_gb >= 7.5:
        return HardwareTier.PRO

    # Standard: ≥14GB RAM or GPU with some VRAM
    if ram_gb >= 14 or (has_gpu and vram_gb >= 3):
        return HardwareTier.STANDARD

    # Lite: everything else
    return HardwareTier.LITE
