"""
Woody Kernel — Top-level orchestration and lifecycle management.

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
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


from woody.kernel.config import WoodyConfig, load_config
from woody.kernel.dispatch import DispatchBus, build_dispatch_bus
from woody.memory.episodic import EpisodicMemory
from woody.memory.semantic import SemanticMemory
from woody.memory.working import KernelMemory, RequestContext
from woody.observability.audit_log import AuditLog
from woody.observability.telemetry import Telemetry
from woody.planner.planner import Planner
from woody.planner.working_memory import WorkingMemoryState, is_all_done
from woody.critic.critic import Critic
from woody.synthesis.audio_output import AudioOutput
from woody.synthesis.synthesizer import Synthesizer
from woody.synthesis.tts import TTSEngine
from woody.tools.mcp_host import MCPHost
from woody.utils.logging import get_logger, setup_logging
from woody.utils.groq_client import GroqClient

log = get_logger(__name__)

# ── Global kernel instance (singleton for UI access) ──────────────────────────
_kernel_instance: "WoodyKernel | None" = None


def get_kernel() -> "WoodyKernel | None":
    return _kernel_instance


class WoodyKernel:
    """
    The Woody Kernel — central orchestrator of the entire AI pipeline.

    Components wired together here:
      Perception → Planner → DispatchBus → Critic → Synthesizer → TTS
    """

    def __init__(self, config: WoodyConfig) -> None:
        global _kernel_instance
        self.config = config
        self.session_id = str(uuid.uuid4())[:8]
        self._running = False

        # Core components (initialized in start())
        self.llm_client: GroqClient | None = None
        self.ollama: GroqClient | None = None  # Alias for backward compatibility
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
        self._on_speech_transcribed: Any | None = None
        self._on_response_chunk: Any | None = None
        self._on_response_complete: Any | None = None
        self._confirm_callback: Any | None = None

        _kernel_instance = self

    # ── Startup / Shutdown ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Full startup sequence."""
        setup_logging(self.config.log_level)
        log.info("kernel.starting", tier=self.config.tier.value, session=self.session_id)

        # 1. Open memory and audit log
        self._init_memory()

        # 2. Connect to Groq Cloud LLM
        await self._init_llm()

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

        # Close Groq client
        if self.llm_client:
            await self.llm_client.__aexit__(None, None, None)

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

    async def _init_llm(self) -> None:
        """Initialize high-speed Groq Cloud client."""
        self.llm_client = GroqClient(
            default_model=self.config.models.planner,
            timeout=self.config.models.timeout,
        )
        self.ollama = self.llm_client  # Alias
        await self.llm_client.__aenter__()

        is_connected = await self.llm_client.health_check()
        if is_connected:
            log.info("kernel.groq_connected", model=self.config.models.planner)
        else:
            log.warning(
                "kernel.groq_api_key_missing",
                hint=(
                    "Groq API key not set or invalid!\n"
                    "  1. Get a free API key: https://console.groq.com/keys\n"
                    "  2. Add your key to .env: GROQ_API_KEY=gsk_..."
                ),
            )

    def _init_pipeline(self) -> None:
        cfg = self.config
        assert self.llm_client

        self.critic = Critic(
            client=self.llm_client,
            model=cfg.models.critic,
            use_heuristics=(cfg.tier.value in ("lite", "standard")),
        )

        self.planner = Planner(
            client=self.llm_client,
            router_model=cfg.models.router,
            planner_model=cfg.models.planner,
            session_id=self.session_id,
        )

        self.dispatch = build_dispatch_bus(
            config=cfg,
            ollama_client=self.llm_client,
            confirm_callback=self._confirm_callback,
            critic=self.critic,
        )

        tone = self.semantic.get().tone if self.semantic else "concise"
        self.synthesizer = Synthesizer(
            client=self.llm_client,
            model=cfg.models.synthesizer,
            tone=tone,
        )

        self.tts = TTSEngine(
            engine=cfg.synthesis.tts_engine,
            model_path=cfg.synthesis.piper_model_path,
            config_path=cfg.synthesis.piper_config_path,
            voice=getattr(cfg.synthesis, "tts_voice", "Avery"),
            pet_voice=getattr(cfg.synthesis, "pet_voice", "community-blcuaurhzmvi"),
            rate=cfg.synthesis.tts_rate,
            volume=cfg.synthesis.tts_volume,
            stream=cfg.synthesis.tts_stream,
            inworld_api_key=getattr(cfg.synthesis, "inworld_api_key", ""),
            inworld_model=getattr(cfg.synthesis, "inworld_model", "inworld-tts-2"),
            delivery_mode=getattr(cfg.synthesis, "delivery_mode", "CREATIVE"),
            language=getattr(cfg.synthesis, "language", "AUTO"),
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
        loop = asyncio.get_running_loop()

        # STT
        from woody.perception.stt import STTEngine
        self._stt = STTEngine(
            model=cfg.stt_model,
            device=cfg.stt_device,
            language=cfg.stt_language,
            beam_size=cfg.stt_beam_size,
        )
        self._stt.load()

        # VAD
        if cfg.vad_enabled:
            from woody.perception.vad import VADListener
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
            from woody.perception.wake_word import WakeWordDetector
            self._wake_word = WakeWordDetector(
                engine=cfg.wake_word_engine,
                phrase=cfg.wake_word_phrase,
                threshold=cfg.wake_word_threshold,
                on_wake=self._handle_wake_word,
                porcupine_key=cfg.porcupine_key,
            )
            self._wake_word.start()

        # Screen watcher
        if cfg.screen_enabled:
            from woody.perception.screen import ScreenWatcher
            self._screen = ScreenWatcher(
                event_driven=cfg.screen_event_driven,
                poll_interval_ms=cfg.screen_poll_interval_ms,
                capture_region=cfg.screen_capture_region,
            )
            self._screen.start()

        # Clipboard watcher
        if cfg.clipboard_watch:
            from woody.perception.clipboard import ClipboardWatcher
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

        1. Interrupt any active speech (barge-in)
        2. Get screen and clipboard context
        3. Get conversation dialogue history from kernel working memory
        4. Plan subtasks
        5. Dispatch to agents
        6. Synthesize response
        7. Speak response via TTS & record dialogue turn
        """
        # --- Barge-in: stop any playing speech immediately ---
        self.stop_speaking()

        t0 = time.perf_counter()
        request_id = str(uuid.uuid4())[:8]

        # Record user turn in conversation memory
        self.kernel_memory.add_turn("user", user_text)

        # --- Context gathering ---
        needs_screen = any(w in user_text.lower() for w in ["screen", "display", "window", "see", "look at", "what is on", "what's on", "error", "showing"])
        screen_context = self._get_screen_ocr_text() if needs_screen else ""
        clipboard_context = self._clipboard.get_current() if self._clipboard else ""

        # Formatted multi-turn dialogue memory
        dialogue_history = self.kernel_memory.format_dialogue_for_prompt(n=6)
        task_history = (
            dialogue_history
            or (self.episodic.format_history_for_prompt(n=3) if self.episodic else "")
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
        state["dialogue_history"] = dialogue_history

        # --- Dispatch ---
        assert self.dispatch
        state = await self.dispatch.execute(state)

        # --- Fast-path Response formatting or Synthesize ---
        fast_resp = self._fast_format_response(state)
        final_response = ""
        is_stop_action = any(t.get("action") == "stop_speaking" for t in state.get("subtasks", []))

        sentence_queue: asyncio.Queue[str | None] | None = None
        if self.tts and getattr(self.tts, "engine", "") != "disabled" and not is_stop_action:
            sentence_queue = asyncio.Queue()
            asyncio.create_task(self.tts.speak_sentence_stream(sentence_queue))

        if fast_resp is not None:
            log.info("kernel.fast_response_used", response=fast_resp[:60])
            final_response = fast_resp
            if on_response_chunk:
                on_response_chunk(final_response)
            if sentence_queue and not is_stop_action:
                clauses = self.tts._split_into_sentences(final_response) if self.tts else [final_response]
                for c in clauses:
                    await sentence_queue.put(c)
        else:
            assert self.synthesizer
            tone = self.semantic.get().tone if self.semantic else "concise"
            if on_response_chunk:
                # Streaming mode — extract sentences and natural clauses in real-time as tokens arrive
                sentence_buffer = ""
                clause_regex = re.compile(r'([.!?\n]+|[,;:—]\s+)')
                async for chunk in self.synthesizer.stream(state, tone=tone):
                    on_response_chunk(chunk)
                    final_response += chunk
                    sentence_buffer += chunk

                    while True:
                        m = clause_regex.search(sentence_buffer)
                        if not m:
                            break
                        sent = sentence_buffer[:m.end()].strip()
                        words = sent.split()
                        # Only dispatch if it's a full sentence or a clause with at least 2 words
                        if len(words) >= 2 or any(p in sent for p in '.!?\n'):
                            sentence_buffer = sentence_buffer[m.end():]
                            if sent and sentence_queue:
                                await sentence_queue.put(sent)
                        else:
                            # Not enough words yet for a standalone clause, keep accumulating
                            break

                if sentence_buffer.strip() and sentence_queue:
                    await sentence_queue.put(sentence_buffer.strip())

            else:
                final_response = await self.synthesizer.synthesize(state, tone=tone)
                if sentence_queue:
                    clauses = self.tts._split_into_sentences(final_response) if self.tts else [final_response]
                    for c in clauses:
                        await sentence_queue.put(c)


        # Signal end of speech stream
        if sentence_queue:
            await sentence_queue.put(None)

        state["final_response"] = final_response

        # Record assistant reply in dialogue memory
        if final_response:
            self.kernel_memory.add_turn("assistant", final_response)


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

        # Skip screen OCR for initial_prompt on CPU — OCR (easyocr) on CPU
        # takes 3–5 seconds which blocks every transcription. The Whisper
        # base model handles English well without a prompt bias.
        initial_prompt: str | None = None

        # Run STT in background
        async def _transcribe() -> None:
            result = await self._stt.transcribe_async(
                audio_bytes,
                initial_prompt=initial_prompt,
            )
            if result.text.strip():
                log.info("kernel.transcribed", text=result.text[:60])
                if self._on_speech_transcribed:
                    self._on_speech_transcribed(result.text)
                resp = await self.process_request(
                    result.text,
                    on_response_chunk=self._on_response_chunk,
                )
                if self._on_response_complete:
                    self._on_response_complete(resp)

        asyncio.create_task(_transcribe())

    def _fast_format_response(self, state: WorkingMemoryState) -> str | None:
        """Instantly format simple responses without invoking the synthesizer LLM."""
        subtasks = state.get("subtasks", [])
        if len(subtasks) == 1 and subtasks[0].get("status") == "done":
            task = subtasks[0]
            agent = task.get("agent")
            action = task.get("action")
            res = task.get("result")

            if agent in ("react_agent", "chat_agent") and isinstance(res, str):
                return res
            if action == "chat" and isinstance(res, str):
                return res

            if isinstance(res, dict):
                if action == "open_app":
                    app = task.get("params", {}).get("app_name", "application")
                    return f"{app} is up and ready." if res.get("success") else f"Could not launch {app}: {res.get('error')}"
                elif action == "close_app":
                    app = task.get("params", {}).get("app_name", "application")
                    return f"Closed {app}." if res.get("success") else f"Could not close {app}: {res.get('error')}"
                elif action == "stop_speaking":
                    return "Speech stopped."
                elif action == "get_time_date":
                    return f"It is {res.get('time')} on {res.get('date')}."
                elif action == "get_battery":
                    pct = res.get("percent")
                    plugged = "plugged in and charging" if res.get("plugged_in") else "running on battery"
                    return f"Battery sits at {pct}%, {plugged}." if pct is not None else "No battery detected."
                elif action == "get_system_stats":
                    return f"System check: CPU is at {res.get('cpu_percent')}% and RAM is at {res.get('ram_percent')}%."
                elif action == "get_clipboard":
                    text = res.get("clipboard", "")
                    return f'Found in your clipboard: "{text}"' if text else "Clipboard is currently empty."
                elif action == "take_screenshot":
                    return "Captured your screen. Saved and ready."
                elif action == "maximize_window":
                    return "Window maximized to full view."
                elif action == "minimize_window":
                    return "Window tucked away to the taskbar."
                elif action == "scroll":
                    return f"Scrolled {task.get('params', {}).get('direction', 'down')}."
                elif action == "hotkey":
                    return "Shortcut executed."
                elif action == "compose_email":
                    to_addr = task.get("params", {}).get("to", "")
                    return f"Opened email draft to {to_addr}. You can review it and click Send." if res.get("success") else f"Could not open email client: {res.get('error')}"
                elif action == "set_user_profile":
                    return res.get("message", "User profile updated successfully.")
                elif action == "get_user_profile":
                    name = res.get("name")
                    return f"User name is set to {name}." if name else "No user name is currently configured."
                elif action == "search_web":
                    summary = res.get("summary")
                    if summary:
                        return summary
                    results = res.get("results", [])
                    if results:
                        return "\n".join(f"• {r.get('title', '')}: {r.get('snippet', '')}" for r in results[:3])
                    return f"Here's what I found for '{task.get('params', {}).get('query', '')}'."

                elif action in ("analyze_screen", "describe_window", "read_screen_text", "explain_error"):
                    analysis = res.get("analysis")
                    if analysis:
                        return analysis

            if isinstance(res, str) and len(res) < 500:
                return res

        return None

    def _get_screen_ocr_text(self) -> str:
        """Get current screen OCR text for context (non-blocking best-effort)."""
        try:
            if self._screen:
                capture = self._screen.capture_now()
                if capture:
                    # Lazily initialise the OCR engine once and cache it on self
                    if not hasattr(self, "_ocr_engine"):
                        from woody.perception.ocr import OCREngine
                        ocr = OCREngine(engine=self.config.perception.ocr_engine)
                        ocr.load()
                        self._ocr_engine = ocr
                    result = self._ocr_engine.read_image(capture.image)
                    return result.text[:500]
        except Exception as e:
            log.debug("kernel.ocr_error", error=str(e))
        return ""

    def stop_speaking(self) -> None:
        """Stop any active TTS audio playback immediately."""
        if self.tts:
            self.tts.stop()

    def set_mode(self, mode: str = "normal") -> None:
        """Switch assistant mode between 'normal' (Avery voice) and 'pet' (community-blcuaurhzmvi cat voice)."""
        if self.tts:
            self.tts.set_mode(mode)
        log.info("kernel.mode_set", mode=mode)

    def _handle_wake_word(self) -> None:
        """Invoked when the wake word ('Hey Woody') is spotted."""
        log.info("kernel.wake_word_triggered")
        self.stop_speaking()
        if self.audio:
            self.audio.play_wake_chime()
        if self._on_wake_word:
            self._on_wake_word()

    # ── UI Callback Registration ──────────────────────────────────────────────

    def set_wake_word_callback(self, fn: Any) -> None:
        """Register callback fired when wake word is detected."""
        self._on_wake_word = fn

    def set_speech_start_callback(self, fn: Any) -> None:
        """Register callback fired when speech starts."""
        self._on_speech_start = fn

    def set_speech_transcribed_callback(self, fn: Any) -> None:
        """Register callback fired when speech is transcribed."""
        self._on_speech_transcribed = fn

    def set_response_chunk_callback(self, fn: Any) -> None:
        """Register callback fired on each response token chunk."""
        self._on_response_chunk = fn

    def set_response_complete_callback(self, fn: Any) -> None:
        """Register callback fired when response completes."""
        self._on_response_complete = fn

    def set_confirm_callback(self, fn: Any) -> None:
        """Register async callback for user-confirm tier actions."""
        self._confirm_callback = fn


async def start_kernel_only(config_path: str | None = None) -> None:
    """Start the Woody kernel in headless mode (no GUI)."""
    from rich.console import Console

    console = Console()
    console.print("[bold cyan]Woody Kernel[/bold cyan] starting in headless mode...")

    cfg = load_config(config_path)
    kernel = WoodyKernel(cfg)
    await kernel.start()

    console.print("[bold green]Woody ready.[/bold green] Type your request (Ctrl+C to exit):\n")

    try:
        while True:
            try:
                # Use get_running_loop() — get_event_loop() is deprecated in 3.10+
                loop = asyncio.get_running_loop()
                text = await loop.run_in_executor(None, input, "You: ")
                if text.strip():
                    response = await kernel.process_request(text.strip())
                    console.print(f"[bold]Woody:[/bold] {response}\n")
            except (EOFError, KeyboardInterrupt):
                break
    finally:
        await kernel.stop()
        console.print("[yellow]Woody stopped.[/yellow]")


def cli_start() -> None:
    """CLI entry point for Woody-kernel command."""
    asyncio.run(start_kernel_only())
