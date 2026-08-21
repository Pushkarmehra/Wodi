"""
Wodi Kernel Configuration.

Loads wodi_config.yaml, merges with hardware-detected tier model assignments,
and exposes a typed WodiConfig dataclass used throughout the system.

Usage:
    from wodi.kernel.config import load_config
    cfg = load_config()
    print(cfg.models.planner)  # → "qwen2.5:7b"
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from wodi.utils.hardware import HardwareProfile, HardwareTier, detect_hardware
from wodi.utils.logging import get_logger

log = get_logger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "wodi_config.yaml"


# ── Sub-config dataclasses ────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    provider: str = "groq"
    timeout: float = 30.0
    router: str = "llama-3.1-8b-instant"
    planner: str = "llama-3.3-70b-versatile"
    critic: str = "llama-3.1-8b-instant"
    synthesizer: str = "llama-3.3-70b-versatile"
    vision: str = "llama-3.2-11b-vision-preview"
    embedding: str = ""
    speculative_decoding: bool = False
    draft_model: str = ""


@dataclass
class PerceptionConfig:
    wake_word_enabled: bool = True
    wake_word_engine: str = "openwakeword"
    wake_word_phrase: str = "hey wodi"
    wake_word_threshold: float = 0.5
    porcupine_key: str = ""
    vad_enabled: bool = True
    vad_threshold: float = 0.4
    vad_min_speech_ms: int = 250
    vad_max_silence_ms: int = 800
    stt_model: str = "base"
    stt_device: str = "auto"
    stt_language: str = "en"
    stt_beam_size: int = 5
    stt_use_screen_prompt: bool = True
    screen_enabled: bool = True
    screen_event_driven: bool = True
    screen_poll_interval_ms: int = 500
    screen_capture_region: str = "active_window"
    clipboard_watch: bool = True
    ocr_engine: str = "easyocr"


@dataclass
class AgentConfig:
    desktop_enabled: bool = True
    desktop_timeout: int = 30
    vision_enabled: bool = True
    vision_timeout: int = 45
    browser_enabled: bool = False
    browser_timeout: int = 60
    coding_enabled: bool = False
    coding_timeout: int = 30
    system_enabled: bool = True
    system_timeout: int = 15


@dataclass
class MemoryConfig:
    episodic_enabled: bool = True
    max_sessions: int = 10000
    semantic_enabled: bool = True
    rag_enabled: bool = False
    rag_folders: list[str] = field(default_factory=list)
    preferred_browser: str = "chrome"
    preferred_editor: str = "vscode"
    tone: str = "concise"
    tts_rate: float = 1.0
    tts_voice: str = "en_US-lessac-medium"


@dataclass
class SynthesisConfig:
    tts_engine: str = "piper"
    tts_stream: bool = True
    tts_rate: float = 1.0
    tts_volume: float = 0.85
    piper_model_path: str = "~/.wodi/models/tts/en_US-lessac-medium.onnx"
    piper_config_path: str = "~/.wodi/models/tts/en_US-lessac-medium.onnx.json"


@dataclass
class UIConfig:
    hotkey: str = "ctrl+space"
    orb_position: str = "bottom_right"
    theme: str = "dark"
    high_contrast: bool = False
    show_captions: bool = True
    caption_font_size: int = 14
    confirmation_timeout_seconds: int = 30


@dataclass
class ToolsConfig:
    plugin_dir: str = "plugins"
    auto_allow_read: bool = True
    auto_allow_system_info: bool = True
    confirm_browser_actions: bool = True
    confirm_file_write: bool = True
    block_registry_edits: bool = True
    block_uac_actions: bool = True


@dataclass
class ObservabilityConfig:
    audit_log_enabled: bool = True
    audit_log_path: str = "~/.wodi/audit.db"
    audit_max_entries: int = 100_000
    telemetry_enabled: bool = False
    telemetry_port: int = 9090


@dataclass
class WodiConfig:
    tier: HardwareTier = HardwareTier.STANDARD
    hardware: HardwareProfile | None = None
    data_dir: Path = field(default_factory=lambda: Path("~/.wodi").expanduser())
    log_level: str = "INFO"
    models: ModelConfig = field(default_factory=ModelConfig)
    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)


# ── Loader ────────────────────────────────────────────────────────────────────

def load_config(config_path: str | Path | None = None) -> WodiConfig:
    """
    Load and merge configuration.

    Priority (highest → lowest):
      1. Environment variables (WODI_* prefix)
      2. wodi_config.yaml user config
      3. Hardware-tier model YAML
      4. Dataclass defaults
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}

    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        log.info("config.loaded", path=str(path))
    else:
        log.warning("config.not_found", path=str(path), fallback="defaults")

    # Detect hardware and determine tier
    hw = detect_hardware()
    tier_override = raw.get("general", {}).get("tier", "auto")
    if tier_override != "auto":
        try:
            tier = HardwareTier(tier_override)
        except ValueError:
            log.warning("config.invalid_tier", value=tier_override, fallback="auto")
            tier = hw.tier
    else:
        tier = hw.tier

    # Load tier-specific model YAML
    tier_models = _load_tier_models(tier)

    # Build config
    cfg = WodiConfig(
        tier=tier,
        hardware=hw,
        data_dir=Path(raw.get("general", {}).get("data_dir", "~/.wodi")).expanduser(),
        log_level=raw.get("general", {}).get("log_level", "INFO"),
        models=_build_model_config(raw, tier_models),
        perception=_build_perception_config(raw),
        agents=_build_agent_config(raw),
        memory=_build_memory_config(raw),
        synthesis=_build_synthesis_config(raw),
        ui=_build_ui_config(raw),
        tools=_build_tools_config(raw),
        observability=_build_observability_config(raw),
    )

    # Apply environment variable overrides
    _apply_env_overrides(cfg)

    # Ensure data directory exists
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    log.info(
        "config.ready",
        tier=cfg.tier.value,
        planner=cfg.models.planner,
        tts=cfg.synthesis.tts_engine,
    )
    return cfg


def _load_tier_models(tier: HardwareTier) -> dict[str, Any]:
    tier_file = Path(__file__).parent.parent.parent / "config" / f"models_{tier.value}.yaml"
    if tier_file.exists():
        with open(tier_file, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _build_model_config(raw: dict, tier_models: dict) -> ModelConfig:
    m = raw.get("models", {})
    tm_router = tier_models.get("router", {})
    tm_planner = tier_models.get("planner", {})
    tm_critic = tier_models.get("critic", {})
    tm_synth = tier_models.get("synthesizer", {})
    tm_vision = tier_models.get("vision", {})
    tm_embed = tier_models.get("embedding", {})
    tm_spec = tier_models.get("speculative_decoding", {})

    return ModelConfig(
        provider=m.get("provider", "groq"),
        timeout=float(m.get("timeout", m.get("ollama_timeout", 30))),
        router=m.get("router") or tm_router.get("model", "llama-3.1-8b-instant"),
        planner=m.get("planner") or tm_planner.get("model", "llama-3.3-70b-versatile"),
        critic=m.get("critic") or tm_critic.get("model", "llama-3.1-8b-instant"),
        synthesizer=m.get("synthesizer") or tm_synth.get("model", "llama-3.3-70b-versatile"),
        vision=m.get("vision") or tm_vision.get("model", "llama-3.2-11b-vision-preview"),
        embedding=tm_embed.get("model", ""),
        speculative_decoding=bool(
            tm_spec.get("enabled", False) if isinstance(tm_spec, dict) else tier_models.get("speculative_decoding", False)
        ),
        draft_model=m.get("draft_model") or (
            tm_spec.get("draft_model", "") if isinstance(tm_spec, dict) else ""
        ),
    )


def _build_perception_config(raw: dict) -> PerceptionConfig:
    p = raw.get("perception", {})
    ww = p.get("wake_word", {})
    vad = p.get("vad", {})
    stt = p.get("stt", {})
    screen = p.get("screen", {})
    ocr = p.get("ocr", {})
    return PerceptionConfig(
        wake_word_enabled=bool(ww.get("enabled", True)),
        wake_word_engine=ww.get("engine", "openwakeword"),
        wake_word_phrase=ww.get("phrase", "hey jarvis"),
        wake_word_threshold=float(ww.get("threshold", 0.5)),
        porcupine_key=ww.get("porcupine_key", ""),
        vad_enabled=bool(vad.get("enabled", True)),
        vad_threshold=float(vad.get("threshold", 0.4)),
        vad_min_speech_ms=int(vad.get("min_speech_ms", 250)),
        vad_max_silence_ms=int(vad.get("max_silence_ms", 800)),
        stt_model=stt.get("model", "base"),
        stt_device=stt.get("device", "auto"),
        stt_language=stt.get("language", "en"),
        stt_beam_size=int(stt.get("beam_size", 5)),
        stt_use_screen_prompt=bool(stt.get("use_screen_prompt", True)),
        screen_enabled=bool(screen.get("enabled", True)),
        screen_event_driven=bool(screen.get("event_driven", True)),
        screen_poll_interval_ms=int(screen.get("poll_interval_ms", 500)),
        screen_capture_region=screen.get("capture_region", "active_window"),
        clipboard_watch=bool(p.get("clipboard", {}).get("watch", True)),
        ocr_engine=ocr.get("engine", "easyocr"),
    )


def _build_agent_config(raw: dict) -> AgentConfig:
    a = raw.get("agents", {})
    return AgentConfig(
        desktop_enabled=bool(a.get("desktop", {}).get("enabled", True)),
        desktop_timeout=int(a.get("desktop", {}).get("timeout_seconds", 30)),
        vision_enabled=bool(a.get("vision", {}).get("enabled", True)),
        vision_timeout=int(a.get("vision", {}).get("timeout_seconds", 45)),
        browser_enabled=bool(a.get("browser", {}).get("enabled", False)),
        browser_timeout=int(a.get("browser", {}).get("timeout_seconds", 60)),
        coding_enabled=bool(a.get("coding", {}).get("enabled", False)),
        coding_timeout=int(a.get("coding", {}).get("timeout_seconds", 30)),
        system_enabled=bool(a.get("system", {}).get("enabled", True)),
        system_timeout=int(a.get("system", {}).get("timeout_seconds", 15)),
    )


def _build_memory_config(raw: dict) -> MemoryConfig:
    m = raw.get("memory", {})
    sem = m.get("semantic", {})
    pref = sem.get("preferred_apps", {})
    return MemoryConfig(
        episodic_enabled=bool(m.get("episodic", {}).get("enabled", True)),
        max_sessions=int(m.get("episodic", {}).get("max_sessions", 10000)),
        semantic_enabled=bool(sem.get("enabled", True)),
        rag_enabled=bool(m.get("rag", {}).get("enabled", False)),
        rag_folders=list(m.get("rag", {}).get("folders", [])),
        preferred_browser=pref.get("browser", "chrome"),
        preferred_editor=pref.get("editor", "vscode"),
        tone=sem.get("tone", "concise"),
        tts_rate=float(sem.get("tts_rate", 1.0)),
        tts_voice=sem.get("tts_voice", "en_US-lessac-medium"),
    )


def _build_synthesis_config(raw: dict) -> SynthesisConfig:
    s = raw.get("synthesis", {}).get("tts", {})
    return SynthesisConfig(
        tts_engine=s.get("engine", "piper"),
        tts_stream=bool(s.get("stream", True)),
        tts_rate=float(s.get("rate", 1.0)),
        tts_volume=float(s.get("volume", 0.85)),
        piper_model_path=s.get("piper_model_path", "~/.wodi/models/tts/en_US-lessac-medium.onnx"),
        piper_config_path=s.get("piper_config_path", "~/.wodi/models/tts/en_US-lessac-medium.onnx.json"),
    )


def _build_ui_config(raw: dict) -> UIConfig:
    u = raw.get("ui", {})
    return UIConfig(
        hotkey=u.get("hotkey", "ctrl+space"),
        orb_position=u.get("orb_position", "bottom_right"),
        theme=u.get("theme", "dark"),
        high_contrast=bool(u.get("high_contrast", False)),
        show_captions=bool(u.get("show_captions", True)),
        caption_font_size=int(u.get("caption_font_size", 14)),
        confirmation_timeout_seconds=int(u.get("confirmation_timeout_seconds", 30)),
    )


def _build_tools_config(raw: dict) -> ToolsConfig:
    t = raw.get("tools", {})
    p = t.get("permissions", {})
    return ToolsConfig(
        plugin_dir=t.get("plugin_dir", "plugins"),
        auto_allow_read=bool(p.get("auto_allow_read", True)),
        auto_allow_system_info=bool(p.get("auto_allow_system_info", True)),
        confirm_browser_actions=bool(p.get("confirm_browser_actions", True)),
        confirm_file_write=bool(p.get("confirm_file_write", True)),
        block_registry_edits=bool(p.get("block_registry_edits", True)),
        block_uac_actions=bool(p.get("block_uac_actions", True)),
    )


def _build_observability_config(raw: dict) -> ObservabilityConfig:
    o = raw.get("observability", {})
    al = o.get("audit_log", {})
    tel = o.get("telemetry", {})
    return ObservabilityConfig(
        audit_log_enabled=bool(al.get("enabled", True)),
        audit_log_path=al.get("path", "~/.wodi/audit.db"),
        audit_max_entries=int(al.get("max_entries", 100_000)),
        telemetry_enabled=bool(tel.get("enabled", False)),
        telemetry_port=int(tel.get("export_port", 9090)),
    )


def _apply_env_overrides(cfg: WodiConfig) -> None:
    """Apply WODI_* environment variable overrides."""
    env_map = {
        "WODI_OLLAMA_HOST": ("models", "ollama_host"),
        "WODI_PLANNER_MODEL": ("models", "planner"),
        "WODI_LOG_LEVEL": (None, "log_level"),
    }
    for env_key, (section, attr) in env_map.items():
        val = os.environ.get(env_key)
        if val:
            if section:
                setattr(getattr(cfg, section), attr, val)
            else:
                setattr(cfg, attr, val)
