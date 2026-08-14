"""
Wodi Kernel — Top-level orchestration and lifecycle management.

Startup sequence:
  1. Load config (hardware detect → model tier)
  2. Health-check Ollama (retry if not running)
  3. Initialize: memory, audit log, MCP host, agents, planner, critic, synthesizer
  4. Start perception: wake word, VAD, STT, screen watcher, clipboard watcher
  5. Enter the main async event loop
  6. On each user input: Plan → Dispatch → Critic → Synthesize → TTS

Graceful degradation:
  - GPU unavailable → CPU model tier
  - Ollama not running → retry with guidance
  - STT fails → fallback to text input only
"""
from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

from wodi.kernel.config import WodiConfig, load_config
from wodi.kernel.dispatch import DispatchBus, build_dispatch_bus
from wodi.memory.episodic import EpisodicMemory
from wodi.memory.semantic import SemanticMemory
from wodi.memory.working import KernelMemory, RequestContext
from wodi.observability.audit_log import AuditLog
from wodi.observability.telemetry import Telemetry
from wodi.planner.planner import Planner
from wodi.planner.working_memory import WorkingMemoryState, is_all_done
from wodi.critic.critic import Critic
from wodi.synthesis.audio_output import AudioOutput
from wodi.synthesis.synthesizer import Synthesizer
from wodi.synthesis.tts import TTSEngine
from wodi.tools.mcp_host import MCPHost
from wodi.utils.logging import get_logger, setup_logging
from wodi.utils.ollama_client import OllamaClient

log = get_logger(__name__)

# ── Global kernel instance (singleton for UI access) ──────────────────────────
_kernel_instance: "WodiKernel | None" = None


def get_kernel() -> "WodiKernel | None":
    return _kernel_instance


class WodiKernel:
    """
    The Wodi Kernel — central orchestrator of the entire AI pipeline.

    Components wired together here:
      Perception → Planner → DispatchBus → Critic → Synthesizer → TTS
    """

    def __init__(self, config: WodiConfig) -> None:
        global _kernel_instance
        self.config = config
        self.session_id = str(uuid.uuid4())[:8]
        self._running = False

        # Core components (initialized in start())
        self.ollama: OllamaClient | None = None
        self.planner: Planner | None = None
        self.dispatch: DispatchBus | None = None
        self.critic: Critic | None = None
        self.synthesizer: Synthesizer | None = None
        self.tts: TTSEngine | None = None
        self.audio: AudioOutput | None = None
        self.mcp_host: MCPHost | None = None
        self.audit_log: AuditLog | None = None
        self.episodic: EpisodicMemory | None = None
        self.semantic: SemanticMemory | None = None
        self.telemetry: Telemetry = Telemetry()
        self.kernel_memory: KernelMemory = KernelMemory()

        # Perception components
        self._wake_word: Any | None = None
        self._vad: Any | None = None
        self._stt: Any | None = None
        self._screen: Any | None = None
        self._clipboard: Any | None = None

        # UI callbacks
        self._on_wake_word: Any | None = None
        self._on_speech_start: Any | None = None
        self._on_response_chunk: Any | None = None
        self._confirm_callback: Any | None = None

        _kernel_instance = self

    # ── Startup / Shutdown ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Full startup sequence."""
        setup_logging(self.config.log_level)
        log.info("kernel.starting", tier=self.config.tier.value, session=self.session_id)

        # 1. Open memory and audit log
        self._init_memory()

        # 2. Connect to Ollama
        await self._init_ollama()

        # 3. Build the AI pipeline
        self._init_pipeline()

        # 4. Start MCP host
        self._init_mcp()

        # 5. Start perception layer
        self._init_perception()

        self._running = True
        log.info(
            "kernel.ready",
            planner=self.config.models.planner,
            tier=self.config.tier.value,
            tts=self.config.synthesis.tts_engine,
        )

    async def stop(self) -> None:
        """Graceful shutdown."""
        log.info("kernel.stopping")
        self._running = False

        # Stop perception
        if self._wake_word:
            self._wake_word.stop()
        if self._vad:
            self._vad.stop()
        if self._screen:
            self._screen.stop()
        if self._clipboard:
            self._clipboard.stop()
        if self._stt:
            self._stt.unload()

        # Stop MCP host
        if self.mcp_host:
            self.mcp_host.stop()

        # Close memory
        if self.episodic:
            self.episodic.close()
        if self.audit_log:
            self.audit_log.close()

        # Close Ollama client
        if self.ollama:
            await self.ollama.__aexit__(None, None, None)

        log.info("kernel.stopped")

    # ── Initialization Helpers ────────────────────────────────────────────────

    def _init_memory(self) -> None:
        cfg = self.config
        self.audit_log = AuditLog(
            path=cfg.observability.audit_log_path,
            max_entries=cfg.observability.audit_max_entries,
        )
        if cfg.observability.audit_log_enabled:
            self.audit_log.open()

        if cfg.memory.episodic_enabled:
            self.episodic = EpisodicMemory(
                db_path=cfg.data_dir / "episodic.db"
            )
            self.episodic.open()

        if cfg.memory.semantic_enabled:
            self.semantic = SemanticMemory(
                path=cfg.data_dir / "preferences.json"
            )
            self.semantic.load()

        log.info("kernel.memory_ready")

    async def _init_ollama(self) -> None:
        self.ollama = OllamaClient(
            host=self.config.models.ollama_host,
            timeout=self.config.models.ollama_timeout,
        )
        await self.ollama.__aenter__()

        # Health check with retries
        for attempt in range(3):
            if await self.ollama.health_check():
                log.info("kernel.ollama_connected", host=self.config.models.ollama_host)
                return
            log.warning(
                "kernel.ollama_unavailable",
                attempt=attempt + 1,
                hint="Start Ollama with: ollama serve",
            )
            await asyncio.sleep(2)

        log.error(
            "kernel.ollama_unreachable",
            hint=(
                "Ollama is not running!\n"
                "  1. Install: https://ollama.com\n"
                "  2. Run: ollama serve\n"
                "  3. Pull a model: ollama pull qwen2.5:7b"
            ),
        )
        # Don't crash — operate in degraded mode

    def _init_pipeline(self) -> None:
        cfg = self.config
        assert self.ollama

        self.critic = Critic(
            client=self.ollama,
            model=cfg.models.critic,
            use_heuristics=(cfg.tier.value == "lite"),
        )

        self.planner = Planner(
            client=self.ollama,
            router_model=cfg.models.router,
            planner_model=cfg.models.planner,
            session_id=self.session_id,
        )

        self.dispatch = build_dispatch_bus(
            config=cfg,
            ollama_client=self.ollama,
            confirm_callback=self._confirm_callback,
            critic=self.critic,
        )

        tone = self.semantic.get().tone if self.semantic else "concise"
        self.synthesizer = Synthesizer(
            client=self.ollama,
            model=cfg.models.synthesizer,
            tone=tone,
        )

        self.tts = TTSEngine(
            engine=cfg.synthesis.tts_engine,
            model_path=cfg.synthesis.piper_model_path,
            config_path=cfg.synthesis.piper_config_path,
            rate=cfg.synthesis.tts_rate,
            volume=cfg.synthesis.tts_volume,
        )
        self.tts.load()

        self.audio = AudioOutput(
            volume=cfg.synthesis.tts_volume,
        )

        log.info("kernel.pipeline_ready")


    def _init_mcp(self) -> None:
        self.mcp_host = MCPHost(
            plugin_dir=self.config.tools.plugin_dir,
            confirm_callback=self._confirm_callback,
            audit_log=self.audit_log,
            tools_config=self.config.tools,
        )
        self.mcp_host.start()

    def _init_perception(self) -> None:
        cfg = self.config.perception
        loop = asyncio.get_event_loop()

        # STT
        from wodi.perception.stt import STTEngine
        self._stt = STTEngine(
            model=cfg.stt_model,
            device=cfg.stt_device,
            language=cfg.stt_language,
            beam_size=cfg.stt_beam_size,
        )
        self._stt.load()

        # VAD
        if cfg.vad_enabled:
            from wodi.perception.vad import VADListener
            self._vad = VADListener(
                threshold=cfg.vad_threshold,
                min_speech_ms=cfg.vad_min_speech_ms,
                max_silence_ms=cfg.vad_max_silence_ms,
                on_speech_start=self._on_speech_start,
                on_speech_end=self._on_audio_received,
                loop=loop,
            )
            self._vad.start()

        # Wake word
        if cfg.wake_word_enabled:
            from wodi.perception.wake_word import WakeWordDetector
            self._wake_word = WakeWordDetector(
                engine=cfg.wake_word_engine,
                phrase=cfg.wake_word_phrase,
                threshold=cfg.wake_word_threshold,
                on_wake=self._on_wake_word,
                porcupine_key=cfg.porcupine_key,
            )
            self._wake_word.start()

        # Screen watcher
        if cfg.screen_enabled:
            from wodi.perception.screen import ScreenWatcher
            self._screen = ScreenWatcher(
                event_driven=cfg.screen_event_driven,
                poll_interval_ms=cfg.screen_poll_interval_ms,
                capture_region=cfg.screen_capture_region,
            )
            self._screen.start()

        # Clipboard watcher
        if cfg.clipboard_watch:
            from wodi.perception.clipboard import ClipboardWatcher
            self._clipboard = ClipboardWatcher()
            self._clipboard.start()

        log.info("kernel.perception_ready")

    # ── Core Processing Pipeline ──────────────────────────────────────────────

    async def process_request(
        self,
        user_text: str,
        on_response_chunk: Any | None = None,
    ) -> str:
        """
        Full end-to-end pipeline: text in → spoken+displayed response.

        1. Get screen and clipboard context
        2. Get task history from episodic memory
        3. Plan subtasks
        4. Dispatch to agents
        5. Synthesize response
        6. Speak response via TTS

        Returns the final response text.
        """
        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())[:8]
        log.info("kernel.process_start", request=user_text[:60], id=request_id)

        # --- Context gathering ---
        screen_context = self._get_screen_ocr_text()
        clipboard_context = self._clipboard.get_current() if self._clipboard else ""
        task_history = (
            self.episodic.format_history_for_prompt(n=3) if self.episodic else ""
        )

        # --- Plan ---
        assert self.planner
        state = await self.planner.plan(
            user_request=user_text,
            screen_context=screen_context,
            clipboard_context=clipboard_context,
            task_history=task_history,
        )
        state["session_id"] = self.session_id

        # --- Dispatch ---
        assert self.dispatch
        state = await self.dispatch.execute(state)

        # --- Synthesize ---
        assert self.synthesizer
        tone = self.semantic.get().tone if self.semantic else "concise"
        final_response = ""

        if on_response_chunk:
            # Streaming mode
            async for chunk in self.synthesizer.stream(state, tone=tone):
                on_response_chunk(chunk)
                final_response += chunk
        else:
            final_response = await self.synthesizer.synthesize(state, tone=tone)

        state["final_response"] = final_response

        # --- TTS ---
        if self.tts and final_response:
            await self.tts.speak(final_response)

        # --- Log to episodic memory ---
        duration_ms = (time.perf_counter() - t0) * 1000
        success = any(t["status"] == "done" for t in state["subtasks"])
        if self.episodic:
            self.episodic.log_session(
                session_id=self.session_id,
                user_request=user_text,
                intent=state.get("intent", ""),
                result_summary=final_response[:200],
                success=success,
                duration_ms=duration_ms,
                tool_call_count=len(state.get("tool_call_trace", [])),
            )

        # --- Telemetry ---
        self.telemetry.record_action(
            action="process_request",
            agent="kernel",
            latency_ms=duration_ms,
            success=success,
        )
        self.telemetry.record_tokens(state.get("planner_tokens_used", 0))

        log.info(
            "kernel.process_complete",
            id=request_id,
            duration_ms=f"{duration_ms:.0f}",
            success=success,
        )
        return final_response


    def _on_audio_received(self, audio_bytes: bytes) -> None:
        """Called by VAD when a speech utterance ends."""
        if not self._running or self._stt is None:
            return

        # Get screen OCR for prompt biasing
        initial_prompt = self._get_screen_ocr_text()[:200] if self.config.perception.stt_use_screen_prompt else None

        # Run STT in background
        async def _transcribe() -> None:
            result = await self._stt.transcribe_async(
                audio_bytes,
                initial_prompt=initial_prompt,
            )
            if result.text.strip():
                log.info("kernel.transcribed", text=result.text[:60])
                await self.process_request(result.text)

        asyncio.create_task(_transcribe())

    def _get_screen_ocr_text(self) -> str:
        """Get current screen OCR text for context (non-blocking best-effort)."""
        try:
            if self._screen:
                capture = self._screen.capture_now()
                if capture and self._stt:
                    from wodi.perception.ocr import OCREngine
                    ocr = OCREngine(engine=self.config.perception.ocr_engine)
                    if not hasattr(self, "_ocr_engine"):
                        ocr.load()
                        self._ocr_engine = ocr
                    result = self._ocr_engine.read_image(capture.image)
                    return result.text[:500]
        except Exception as e:
            log.debug("kernel.ocr_error", error=str(e))
        return ""

    # ── UI Callback Registration ──────────────────────────────────────────────

    def set_wake_word_callback(self, fn: Any) -> None:
        """Register callback fired when wake word is detected."""
        self._on_wake_word = fn

    def set_speech_start_callback(self, fn: Any) -> None:
        """Register callback fired when speech starts."""
        self._on_speech_start = fn

    def set_confirm_callback(self, fn: Any) -> None:
        """Register async callback for user-confirm tier actions."""
        self._confirm_callback = fn


async def start_kernel_only(config_path: str | None = None) -> None:
    """Start the Wodi kernel in headless mode (no GUI)."""
    from rich.console import Console
    console = Console()
    console.print("[bold cyan]Wodi Kernel[/bold cyan] starting in headless mode...")

    cfg = load_config(config_path)
    kernel = WodiKernel(cfg)
    await kernel.start()

    console.print("[bold green]Wodi ready.[/bold green] Type your request (Ctrl+C to exit):\n")

    try:
        while True:
            try:
                text = await asyncio.get_event_loop().run_in_executor(None, input, "You: ")
                if text.strip():
                    response = await kernel.process_request(text.strip())
                    console.print(f"[bold]Wodi:[/bold] {response}\n")
            except (EOFError, KeyboardInterrupt):
                break
    finally:
        await kernel.stop()
        console.print("[yellow]Wodi stopped.[/yellow]")


def cli_start() -> None:
    """CLI entry point for wodi-kernel command."""
    asyncio.run(start_kernel_only())
