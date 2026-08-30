"""
Woody VPet Simulator — Authentic Full-Featured VPet Desktop Companion for Windows.
Theme: Purple (VPet prupe.lps) | Language: English

Directly powers the character using all 6,180+ official animation frames from
`vpet/VPet-main/VPet-Simulator.Windows/mod/0000_core/`:
  • Native VPet Graph Animation Engine (vpet_graph.py): Exact frame-by-frame timing
    across all 25 official actions (Idle, Meow, Tennis, Bubbles, Squat, Yawning, Music,
    Gift, BDay, Touch Head, Touch Body, Eat, Drink, Pinch, Sleep, Work, Move, Say, LevelUP).
  • Authentic In-Game 5-Tab Floating Toolbar (Feed, Status, Interact, Shop, Chat, Close)
    with Royal Purple styling (#7c3aed / #a855f7 / #1e1338).
  • Detailed VPet Stat Gauges (Level, Money $, EXP, Stamina, Mood, Hunger, Thirst).
  • Floating Purple VPet WorkTimer during active jobs.
  • VPet MessageBar Speech Dialogue Box with Inworld Neural Voice ("community-blcuaurhzmvi")
    and Groq LLaMA 3.3 70B AI Brain.
  • 120+ VPet Items loaded from official LPS files with full English translation.
  • Persistence: Auto-saves state to ~/.woody/vpet_save.json.
"""
from __future__ import annotations

import asyncio
import base64
import ctypes
import json
import os
import random
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from woody.ui.vpet_engine import VPetEngine, ITEMS_CATALOG, JOBS_CATALOG, Item, JobTask
from woody.ui.vpet_graph import VPetGraphEngine, VPET_VUP_DIR, FALLBACK_GIF_DIR
from woody.utils.logging import get_logger

log = get_logger(__name__)

# Default Voice IDs & Asset Paths
PET_VOICE_INWORLD = "community-blcuaurhzmvi"
NORMAL_VOICE_DEFAULT = "Avery"
GIF_DIR = FALLBACK_GIF_DIR

# ── VPet Purple Theme Color Palette (from theme/prupe.lps) ───────────────────
C_BG_PANEL = "#1e1338"          # Deep Velvet Purple panel background
C_BG_CARD = "#271747"           # Card / list item background
C_PRIMARY = "#7c3aed"           # Royal Violet primary brand
C_PRIMARY_LIGHT = "#a855f7"     # Bright Purple highlight
C_PRIMARY_HOVER = "#9333ea"     # Active button hover
C_BORDER = "#8b5cf6"            # Crisp Purple border
C_TEXT_LIGHT = "#f3e8ff"        # Crisp readable light violet text
C_TEXT_MUTED = "#c4b5fd"        # Soft secondary text
C_GOLD = "#fbbf24"              # Radiant Gold currency color


def _play_sound_cue(cue_type: str = "purr") -> None:
    """Subtle audio feedback cues."""
    def _worker():
        try:
            import winsound
            if cue_type == "purr":
                for freq in (420, 480, 540, 600):
                    winsound.Beep(freq, 35)
            elif cue_type == "feed":
                winsound.Beep(520, 50)
                winsound.Beep(680, 60)
                winsound.Beep(840, 80)
            elif cue_type == "fanfare":
                for freq in (523, 659, 784, 1046):
                    winsound.Beep(freq, 85)
            elif cue_type == "coin":
                winsound.Beep(988, 60)
                winsound.Beep(1318, 90)
            elif cue_type == "chime":
                winsound.Beep(880, 60)
                winsound.Beep(1100, 80)
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()


class WoodyAIPet:
    """
    Complete VPet Desktop AI Companion with Native Graph Animation & Purple Theme.
    """

    def __init__(
        self,
        root: tk.Tk | None = None,
        server_url: str = "http://127.0.0.1:8765",
        pet_voice: str = PET_VOICE_INWORLD,
    ) -> None:
        self.window = root or tk.Tk()
        self.server_url = server_url
        self.pet_voice = pet_voice

        # VPet Simulation Engine
        self.vpet = VPetEngine(on_level_up=self._on_level_up)

        # Native VPet Graph Animation Player (6,180+ frames)
        self.graph = VPetGraphEngine(target_size=(220, 220), master=self.window)

        # Inworld Voice API key
        self.inworld_api_key = os.getenv("INWORLD_API_KEY", "").strip()
        if not self.inworld_api_key:
            env_file = Path(__file__).parent.parent.parent / ".env"
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("INWORLD_API_KEY="):
                            self.inworld_api_key = line.split("=", 1)[1].strip().strip('"\'')
                except Exception:
                    pass

        # Screen & Window Geometry
        self.screen_width = self.window.winfo_screenwidth()
        self.screen_height = self.window.winfo_screenheight()
        self.pet_width = 380
        self.pet_height = 370
        self.x = random.randint(200, max(250, self.screen_width - 450))
        self.floor_y = self.screen_height - 245
        self.y = self.floor_y
        self.walk_speed = 4

        # Active Animation State
        self.current_action: str = "startup"
        self.current_frames: list[tuple[Any, int]] = []
        self.frame_idx: int = 0
        self.is_transient_action: bool = False
        self.anim_timer: Any | None = None

        # Dragging & UI state
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_mouse_root_x = 0
        self.drag_mouse_root_y = 0
        self.has_dragged = False
        self.is_thinking = False
        self.is_sleeping = False
        self.toolbar_visible = False
        self.panel_visible = False

        self.bubble_timer: Any | None = None
        self.ambient_timer: Any | None = None
        self.toolbar_leave_timer: Any | None = None
        self.sim_timer: Any | None = None
        self.motion_timer: Any | None = None

        # Voice Synthesis Engine & Background Streaming Loop for Zero-Latency Speech
        from woody.synthesis.tts import TTSEngine
        self.tts = TTSEngine(
            engine="inworld" if self.inworld_api_key else "edge-tts",
            voice=self.pet_voice,
            pet_voice=self.pet_voice,
            inworld_api_key=self.inworld_api_key,
        )
        try:
            self.tts.load()
        except Exception as e:
            log.debug("desktop_pet.tts_load_err", error=str(e))

        self._voice_loop = asyncio.new_event_loop()
        self._voice_thread = threading.Thread(target=self._run_voice_loop, daemon=True)
        self._voice_thread.start()
        self._active_voice_queue: asyncio.Queue[str | None] | None = None

        # Fallback GIF frame compatibility for unit tests
        self._load_fallback_gif_frames()

        # Build UI & Bind Events
        self._setup_window()
        self._build_vpet_ui()
        self._bind_events()

        # Play authentic VPet startup greeting sequence
        self.set_action("startup", loop=False)
        self.sim_timer = self.window.after(1000, self._vpet_simulation_tick)
        self.motion_timer = self.window.after(8000, self._schedule_spontaneous_motion)

        # Initial greeting in English
        lvl = self.vpet.stats.level
        self.say(f"Level {lvl} {self.vpet.stats.name} Ready! Click me or hover for VPet Toolbar 🐾", timeout_s=6, speak_voice=False)
        _play_sound_cue("purr")
        self._schedule_ambient_thought(initial_delay_ms=30000)

    def _run_voice_loop(self) -> None:
        asyncio.set_event_loop(self._voice_loop)
        self._voice_loop.run_forever()

    def _load_fallback_gif_frames(self) -> None:
        """Expose standard frame lists for unit test compatibility."""
        self.frames_idle: list[tk.PhotoImage] = []
        self.frames_idle_to_sleep: list[tk.PhotoImage] = []
        self.frames_sleep: list[tk.PhotoImage] = []
        self.frames_sleep_to_idle: list[tk.PhotoImage] = []
        self.frames_walk_left: list[tk.PhotoImage] = []
        self.frames_walk_right: list[tk.PhotoImage] = []

        gif_map = {
            "idle": ["idle.gif", "1_TxQeilWhJIVCemtG856ZUg.gif"],
            "idle_to_sleep": ["idle_to_sleep.gif", "1_0Ev3tmHS1YzGduwLM11_kA.gif"],
            "sleep": ["sleep.gif", "1_ageFzVJEctK88GuR0EuRIA.gif"],
            "sleep_to_idle": ["sleep_to_idle.gif", "1_j0S7mwpy0nrdCEYafE3cEw.gif"],
            "walk_left": ["walk_negative.gif", "1_wKYgYE_uaPVd0-QFantclA.gif"],
            "walk_right": ["walk_positive.gif", "1_6eBKCdbUsBdJJQumlWndww.gif"],
        }

        def _load(keys: list[str]) -> list[tk.PhotoImage]:
            for k in keys:
                p = FALLBACK_GIF_DIR / k
                if p.exists():
                    frames = []
                    for i in range(12):
                        try:
                            frames.append(tk.PhotoImage(file=str(p), format=f"gif -index {i}"))
                        except Exception:
                            break
                    if frames:
                        return frames
            return []

        self.frames_idle = _load(gif_map["idle"])
        self.frames_idle_to_sleep = _load(gif_map["idle_to_sleep"])
        self.frames_sleep = _load(gif_map["sleep"])
        self.frames_sleep_to_idle = _load(gif_map["sleep_to_idle"])
        self.frames_walk_left = _load(gif_map["walk_left"])
        self.frames_walk_right = _load(gif_map["walk_right"])

    def _setup_window(self) -> None:
        self.window.overrideredirect(True)
        self.window.wm_attributes("-topmost", True)
        self.window.config(bg="black")
        self.window.wm_attributes("-transparentcolor", "black")
        self.window.geometry(f"{self.pet_width}x{self.pet_height}+{self.x - 100}+{self.y - 170}")

    # ── Native VPet Graph Animation Player Loop ───────────────────────────────

    def set_action(self, action_name: str, loop: bool = True, on_finish: Callable[[], None] | None = None) -> None:
        """Switch active animation sequence with native VPet frame durations."""
        frames = self.graph.load_sequence(action_name)
        if not frames:
            frames = self.graph.load_sequence("idle")

        self.current_action = action_name
        self.current_frames = frames
        self.frame_idx = 0
        self.is_transient_action = not loop
        self.on_action_finish = on_finish

        if self.anim_timer:
            self.window.after_cancel(self.anim_timer)
        self._render_current_frame()

    def _render_current_frame(self) -> None:
        """Display active frame and schedule next frame according to native duration."""
        if not self.current_frames:
            return

        photo, dur_ms = self.current_frames[self.frame_idx]
        self.pet_label.configure(image=photo)
        self.pet_label.image = photo

        if self.frame_idx < len(self.current_frames) - 1:
            self.frame_idx += 1
            self.anim_timer = self.window.after(dur_ms, self._render_current_frame)
        else:
            if self.is_transient_action:
                if self.on_action_finish:
                    self.on_action_finish()
                else:
                    if self.vpet.active_job:
                        self.set_action("work_coding", loop=True)
                    elif self.is_sleeping:
                        self.set_action("sleep", loop=True)
                    else:
                        self.set_action("idle", loop=True)
            else:
                self.frame_idx = 0
                self.anim_timer = self.window.after(dur_ms, self._render_current_frame)

    # ── Purple Theme VPet UI Construction (100% English) ──────────────────────

    def _build_vpet_ui(self) -> None:
        # 1. Detailed Character Status Panel (winCharacterPanel.xaml in Purple)
        self.stats_panel = tk.Frame(
            self.window,
            bg=C_BG_PANEL,
            bd=0,
            highlightthickness=2,
            highlightbackground=C_BORDER,
        )

        p_hdr = tk.Frame(self.stats_panel, bg=C_BG_PANEL)
        p_hdr.pack(fill="x", padx=8, pady=(4, 2))

        self.p_title_lbl = tk.Label(
            p_hdr,
            text=f"⭐ Lv.{self.vpet.stats.level} {self.vpet.stats.name}",
            bg=C_BG_PANEL,
            fg=C_TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self.p_title_lbl.pack(side="left")

        self.p_gold_lbl = tk.Label(
            p_hdr,
            text=f"🪙 ${self.vpet.stats.money:,}",
            bg=C_BG_PANEL,
            fg=C_GOLD,
            font=("Segoe UI", 9, "bold"),
        )
        self.p_gold_lbl.pack(side="right")

        self.bars_grid = tk.Frame(self.stats_panel, bg=C_BG_PANEL)
        self.bars_grid.pack(fill="x", padx=8, pady=(0, 6))

        self.bar_labels: dict[str, tuple[tk.Label, ttk.Progressbar, tk.Label]] = {}
        bar_defs = [
            ("EXP Experience", "exp"),
            ("Stamina", "energy"),
            ("Mood / Feeling", "mood"),
            ("Hunger / Food", "fullness"),
            ("Thirst / Water", "thirst"),
        ]

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Purple.Horizontal.TProgressbar", thickness=10, troughcolor="#130b24", bordercolor=C_BG_PANEL, lightcolor=C_PRIMARY, darkcolor=C_PRIMARY)

        for row_idx, (label_txt, stat_key) in enumerate(bar_defs):
            name_lbl = tk.Label(
                self.bars_grid,
                text=label_txt,
                bg=C_BG_PANEL,
                fg=C_TEXT_MUTED,
                font=("Segoe UI", 7, "bold"),
                anchor="w",
                width=14,
            )
            name_lbl.grid(row=row_idx, column=0, sticky="w", pady=1)

            pb = ttk.Progressbar(
                self.bars_grid,
                orient="horizontal",
                length=135,
                mode="determinate",
                style="Purple.Horizontal.TProgressbar",
            )
            pb.grid(row=row_idx, column=1, padx=4, pady=1)

            val_lbl = tk.Label(
                self.bars_grid,
                text="100%",
                bg=C_BG_PANEL,
                fg=C_TEXT_LIGHT,
                font=("Segoe UI", 7, "bold"),
                width=6,
                anchor="e",
            )
            val_lbl.grid(row=row_idx, column=2, sticky="e", pady=1)

            self.bar_labels[stat_key] = (name_lbl, pb, val_lbl)

        # 2. In-Game 5-Tab Floating ToolBar (Purple Theme)
        self.toolbar_frame = tk.Frame(
            self.window,
            bg=C_PRIMARY,
            bd=0,
            highlightthickness=1,
            highlightbackground=C_PRIMARY_LIGHT,
        )

        t_btn_style = {
            "bg": C_PRIMARY,
            "fg": "#ffffff",
            "activebackground": C_PRIMARY_HOVER,
            "activeforeground": "#ffffff",
            "font": ("Segoe UI", 8, "bold"),
            "bd": 0,
            "padx": 6,
            "pady": 3,
            "relief": "flat",
            "cursor": "hand2",
        }

        self.tb_feed = tk.Button(self.toolbar_frame, text="🍲 Feed", command=self._open_feed_quickmenu, **t_btn_style)
        self.tb_feed.pack(side="left", padx=1)

        self.tb_panel = tk.Button(self.toolbar_frame, text="📊 Status", command=self._toggle_stats_panel, **t_btn_style)
        self.tb_panel.pack(side="left", padx=1)

        self.tb_interact = tk.Button(self.toolbar_frame, text="🎮 Interact", command=self._open_interact_quickmenu, **t_btn_style)
        self.tb_interact.pack(side="left", padx=1)

        self.tb_shop = tk.Button(self.toolbar_frame, text="🛍️ Shop", command=self._open_betterbuy_shop, **t_btn_style)
        self.tb_shop.pack(side="left", padx=1)

        self.tb_chat = tk.Button(self.toolbar_frame, text="💬 Chat", command=self._show_input, **t_btn_style)
        self.tb_chat.pack(side="left", padx=1)

        self.tb_close = tk.Button(self.toolbar_frame, text="✕", command=self.close, **t_btn_style)
        self.tb_close.pack(side="left", padx=1)

        # 3. Floating Purple WorkTimer Widget
        self.worktimer_frame = tk.Frame(
            self.window,
            bg="#170c2e",
            bd=0,
            highlightthickness=2,
            highlightbackground=C_BORDER,
        )
        self.worktimer_title = tk.Label(
            self.worktimer_frame,
            text="⚡ Working: Python AI Coding",
            bg="#170c2e",
            fg=C_TEXT_MUTED,
            font=("Segoe UI", 8, "bold"),
        )
        self.worktimer_title.pack(side="top", fill="x", padx=8, pady=(4, 1))

        self.worktimer_clock = tk.Label(
            self.worktimer_frame,
            text="00:25",
            bg="#170c2e",
            fg="#ffffff",
            font=("Segoe UI", 16, "bold"),
        )
        self.worktimer_clock.pack(side="top", pady=1)

        self.worktimer_reward = tk.Label(
            self.worktimer_frame,
            text="🪙 +$35  ⭐ +45 EXP",
            bg="#170c2e",
            fg=C_GOLD,
            font=("Segoe UI", 7, "bold"),
        )
        self.worktimer_reward.pack(side="top", pady=(0, 4))

        # 4. MessageBar Speech Bubble (Purple Theme & English Header)
        self.messagebar_frame = tk.Frame(
            self.window,
            bg="#160e29",
            bd=0,
            highlightthickness=2,
            highlightbackground=C_BORDER,
        )

        self.messagebar_header = tk.Label(
            self.messagebar_frame,
            text=f"{self.vpet.stats.name} (Virtual Pet):",
            bg="#160e29",
            fg=C_TEXT_MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self.messagebar_header.pack(fill="x", padx=8, pady=(4, 0))

        self.messagebar_text = tk.Label(
            self.messagebar_frame,
            text="✨ I'm listening!",
            bg="#160e29",
            fg="#f8fafc",
            font=("Segoe UI", 8),
            wraplength=310,
            justify="left",
            padx=8,
            pady=4,
        )
        self.messagebar_text.pack(fill="x")

        # 5. Quick Input for AI Chat (Purple Theme)
        self.input_frame = tk.Frame(self.window, bg="black")
        self.input_entry = tk.Entry(
            self.input_frame,
            bg="#1c0f33",
            fg="#ffffff",
            insertbackground=C_PRIMARY_LIGHT,
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=4, pady=2)
        self.input_entry.bind("<Return>", lambda e: self._on_submit_input())
        self.input_entry.bind("<Escape>", lambda e: self._hide_input())

        # 6. Main Pet Avatar Sprite
        self.pet_label = tk.Label(
            self.window,
            bd=0,
            bg="black",
            cursor="hand2",
        )
        self.pet_label.pack(side="bottom", pady=4)

    def _bind_events(self) -> None:
        self.pet_label.bind("<Button-1>", self._on_drag_start)
        self.pet_label.bind("<B1-Motion>", self._on_drag_motion)
        self.pet_label.bind("<ButtonRelease-1>", self._on_drag_end)
        self.pet_label.bind("<Double-Button-1>", lambda e: self._show_input())
        self.pet_label.bind("<Button-3>", self._show_context_menu)

        hover_targets = [
            self.pet_label, self.toolbar_frame, self.stats_panel, self.worktimer_frame,
            self.tb_feed, self.tb_panel, self.tb_interact, self.tb_shop, self.tb_chat, self.tb_close,
            self.messagebar_frame, self.messagebar_text, self.input_frame, self.input_entry
        ]
        for w in hover_targets:
            w.bind("<Enter>", self._on_mouse_enter, add="+")
            w.bind("<Leave>", self._on_mouse_leave, add="+")

        self.messagebar_frame.bind("<Double-Button-1>", lambda e: self._show_input())
        self.messagebar_text.bind("<Double-Button-1>", lambda e: self._show_input())

    # ── Hover & UI Visibility Controls ────────────────────────────────────────

    def _on_mouse_enter(self, event: Any = None) -> None:
        if self.toolbar_leave_timer:
            self.window.after_cancel(self.toolbar_leave_timer)
            self.toolbar_leave_timer = None

        if not self.toolbar_visible:
            self.toolbar_frame.pack(side="top", fill="x", padx=6, pady=2, before=self.pet_label)
            self.toolbar_visible = True
        self._refresh_stats_panel()

    def _on_mouse_leave(self, event: Any = None) -> None:
        if self.toolbar_leave_timer:
            self.window.after_cancel(self.toolbar_leave_timer)
        self.toolbar_leave_timer = self.window.after(850, self._hide_toolbar)

    def _hide_toolbar(self) -> None:
        if self.toolbar_visible:
            self.toolbar_frame.pack_forget()
            self.toolbar_visible = False
        if self.panel_visible:
            self.stats_panel.pack_forget()
            self.panel_visible = False
        self.toolbar_leave_timer = None

    def _toggle_stats_panel(self) -> None:
        if self.panel_visible:
            self.stats_panel.pack_forget()
            self.panel_visible = False
        else:
            self.stats_panel.pack(side="top", fill="x", padx=6, pady=2, before=self.pet_label)
            self.panel_visible = True
            self._refresh_stats_panel()

    def _refresh_stats_panel(self) -> None:
        s = self.vpet.stats
        self.p_title_lbl.config(text=f"⭐ Lv.{s.level} {s.name}")
        self.p_gold_lbl.config(text=f"🪙 ${s.money:,}")

        exp_pct = int((s.exp / max(1, s.max_exp)) * 100)
        self.bar_labels["exp"][1]["value"] = exp_pct
        self.bar_labels["exp"][2].config(text=f"{exp_pct}% (x1.0)")

        self.bar_labels["energy"][1]["value"] = int(s.energy)
        self.bar_labels["energy"][2].config(text=f"{int(s.energy)}% (+1/t)")

        self.bar_labels["mood"][1]["value"] = int(s.mood)
        self.bar_labels["mood"][2].config(text=f"{int(s.mood)}% (+1/t)")

        self.bar_labels["fullness"][1]["value"] = int(s.fullness)
        self.bar_labels["fullness"][2].config(text=f"{int(s.fullness)}% (+1/t)")

        self.bar_labels["thirst"][1]["value"] = int(s.thirst)
        self.bar_labels["thirst"][2].config(text=f"{int(s.thirst)}% (+1/t)")

    # ── Life Simulation & Motion Loop ─────────────────────────────────────────

    def _vpet_simulation_tick(self) -> None:
        events = self.vpet.tick(dt_seconds=1.0, is_sleeping=self.is_sleeping)
        for evt in events:
            _play_sound_cue("coin" if "Finished" in evt else "chime")
            self.say(evt, timeout_s=6, speak_voice=True)

        if self.vpet.active_job:
            secs = max(0, int(self.vpet.job_time_remaining))
            mins, s_rem = divmod(secs, 60)
            self.worktimer_clock.config(text=f"{mins:02d}:{s_rem:02d}")
            verb = "Studying" if self.vpet.active_job.category == "study" else "Working"
            self.worktimer_title.config(text=f"⚡ {verb}: {self.vpet.active_job.name}")
            self.worktimer_reward.config(text=f"🪙 +${self.vpet.active_job.gold_reward}  ⭐ +{self.vpet.active_job.exp_reward} EXP")
            if not self.worktimer_frame.winfo_ismapped():
                self.worktimer_frame.pack(side="top", fill="x", padx=8, pady=2, before=self.pet_label)
        else:
            if self.worktimer_frame.winfo_ismapped():
                self.worktimer_frame.pack_forget()

        if self.panel_visible:
            self._refresh_stats_panel()

        self.sim_timer = self.window.after(1000, self._vpet_simulation_tick)

    def _schedule_spontaneous_motion(self) -> None:
        if not self.is_dragging and not self.vpet.active_job and not self.is_sleeping and not self.is_transient_action:
            # Pick from rich VPet IDEL expressions or walking traversal
            choice = random.choice([
                "walk_left", "walk_right",
                "idle_meow", "idle_meowlook", "idle_bubbles", "idle_tennis",
                "idle_squat", "idle_yawning", "idle_aside", "idle_like520", "music"
            ])
            if choice == "walk_left":
                self._start_walking(direction=-1)
            elif choice == "walk_right":
                self._start_walking(direction=1)
            else:
                self.set_action(choice, loop=False)

        next_delay = random.randint(12000, 25000)
        self.motion_timer = self.window.after(next_delay, self._schedule_spontaneous_motion)

    def _start_walking(self, direction: int = 1, steps: int = 15) -> None:
        action = "move_right" if direction > 0 else "move_left"
        self.set_action(action, loop=True)

        def _step(remaining: int):
            if remaining <= 0 or self.is_dragging or self.vpet.active_job or self.is_sleeping:
                self.set_action("idle", loop=True)
                return

            self.x += (direction * self.walk_speed)
            if self.x < 30:
                self.x = 30
                self._start_walking(direction=1, steps=remaining)
                return
            elif self.x > self.screen_width - 240:
                self.x = self.screen_width - 240
                self._start_walking(direction=-1, steps=remaining)
                return

            self.window.geometry(f"{self.pet_width}x{self.pet_height}+{self.x - 100}+{self.y - 170}")
            self.window.after(120, lambda: _step(remaining - 1))

        _step(steps)

    def _on_level_up(self, new_level: int) -> None:
        _play_sound_cue("fanfare")
        self.set_action("levelup", loop=False)
        self.say(f"🎉 ⭐ LEVEL UP! Reached Level {new_level}! Vitals restored & Bonus Gold rewarded! 🪙", timeout_s=8, speak_voice=True)

    # ── Multi-Zone Mouse Interaction & Dragging ───────────────────────────────

    def _on_drag_start(self, event: tk.Event) -> None:
        self.is_dragging = True
        self.has_dragged = False
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.drag_mouse_root_x = event.x_root
        self.drag_mouse_root_y = event.y_root
        self.set_action("pinch", loop=True)

    def _on_drag_motion(self, event: tk.Event) -> None:
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        if abs(event.x_root - self.drag_mouse_root_x) > 4 or abs(event.y_root - self.drag_mouse_root_y) > 4:
            self.has_dragged = True
        self.x += dx
        self.y += dy
        self.window.geometry(f"{self.pet_width}x{self.pet_height}+{self.x - 100}+{self.y - 170}")

    def _on_drag_end(self, event: tk.Event) -> None:
        self.is_dragging = False
        if not self.has_dragged:
            mood, msg = self.vpet.pet_head()
            _play_sound_cue("purr")
            self.set_action("touch_head" if event.y < 85 else "touch_body", loop=False)
            self._refresh_stats_panel()

            greetings = [
                f"✨ Woody here! Level {self.vpet.stats.level} Windows AI companion ready. What shall we do?",
                "⚡ Woody OS online. All systems nominal! Type or speak your command.",
                "🎯 Ready to automate and answer anything on Windows. What's the plan?",
                f"🐾 Woody at your service! Balance: ${self.vpet.stats.money:,} 🪙. What would you like to execute?",
            ]
            self.say(random.choice(greetings), timeout_s=6, speak_voice=True)
            self._show_input()
            return

        if self.y > self.screen_height - 245:
            self.y = self.floor_y
        self.set_action("idle", loop=True)
        _play_sound_cue("purr")
        self.say("🐾 Landed safely on the floor!", timeout_s=3, speak_voice=True)

    # ── Feeding & Interaction Actions (English) ───────────────────────────────

    def _open_feed_quickmenu(self) -> None:
        menu = tk.Menu(self.window, tearoff=0, bg=C_BG_PANEL, fg=C_TEXT_LIGHT, activebackground=C_PRIMARY, font=("Segoe UI", 9))
        for item_id, count in self.vpet.stats.inventory.items():
            item = ITEMS_CATALOG.get(item_id)
            if item:
                menu.add_command(
                    label=f"{item.icon} {item.name} (x{count})",
                    command=lambda iid=item_id: self._use_bag_item(iid)
                )
        menu.add_separator()
        menu.add_command(label="🛍️ Open BetterBuy Shop", command=self._open_betterbuy_shop)
        menu.tk_popup(self.window.winfo_pointerx(), self.window.winfo_pointery())

    def _open_interact_quickmenu(self) -> None:
        menu = tk.Menu(self.window, tearoff=0, bg=C_BG_PANEL, fg=C_TEXT_LIGHT, activebackground=C_PRIMARY, font=("Segoe UI", 9))
        menu.add_command(label="✨ Touch Head", command=lambda: (self.set_action("touch_head", loop=False), self.pet_cat()))
        menu.add_command(label="💖 Tickle Body", command=lambda: (self.set_action("touch_body", loop=False), self.pet_cat()))
        menu.add_command(label="👁️ Analyze Screen", command=self._analyze_current_screen)
        menu.add_command(label="🎵 Listen to Music", command=lambda: (self.set_action("music", loop=False), self.say("🎶 Grooving to the beat! System running smooth.", timeout_s=4, speak_voice=True)))
        menu.add_command(label="🎾 Play Tennis", command=lambda: (self.set_action("idle_tennis", loop=False), self.say("🎾 Tennis time! Having fun on Windows!", timeout_s=4, speak_voice=True)))
        menu.add_command(label="🫧 Blow Bubbles", command=lambda: (self.set_action("idle_bubbles", loop=False), self.say("🫧 Sparkling bubbles floating everywhere!", timeout_s=4, speak_voice=True)))
        menu.add_command(label="💤 Take a Nap", command=self._toggle_sleep)
        menu.add_separator()
        menu.add_command(label="💼 Work for Gold", command=lambda: self._open_jobs_window("work"))
        menu.add_command(label="📚 Study for EXP", command=lambda: self._open_jobs_window("study"))
        menu.tk_popup(self.window.winfo_pointerx(), self.window.winfo_pointery())

    def _show_context_menu(self, event: tk.Event) -> None:
        menu = tk.Menu(self.window, tearoff=0, bg=C_BG_PANEL, fg=C_TEXT_LIGHT, activebackground=C_PRIMARY, font=("Segoe UI", 9))
        menu.add_command(label="💬 Chat with Woody (Click / Double Click)", command=self._show_input)
        menu.add_command(label="📊 Status & Vitals", command=self._toggle_stats_panel)
        menu.add_command(label="👁️ Analyze Screen", command=self._analyze_current_screen)
        menu.add_command(label="📈 System Health Monitor", command=self._check_system_health)
        menu.add_command(label="🛍️ BetterBuy Item Shop", command=self._open_betterbuy_shop)
        menu.add_command(label="💼 Work Center", command=lambda: self._open_jobs_window("work"))
        menu.add_command(label="📚 Study Center", command=lambda: self._open_jobs_window("study"))
        menu.add_separator()
        menu.add_command(label="🖥️ Switch to Full Web UI", command=self._open_full_gui)
        menu.add_separator()
        menu.add_command(label="❌ Exit Woody Pet", command=self.close)
        menu.tk_popup(event.x_root, event.y_root)

    def _analyze_current_screen(self) -> None:
        """Trigger instant screen capture and vision analysis via Woody's vision tools."""
        self.ask_woody("Analyze the current screen and tell me what is open and visible.")

    def _use_bag_item(self, item_id: str) -> None:
        it = ITEMS_CATALOG.get(item_id)
        if it and it.category == "gift":
            action = "gift"
        elif it and it.category == "drink":
            action = "drink"
        else:
            action = "eat"
        self.set_action(action, loop=False)

        ok, msg = self.vpet.use_item(item_id)
        _play_sound_cue("feed" if ok else "purr")
        self.say(msg, timeout_s=4, speak_voice=ok)
        self._refresh_stats_panel()

    def feed_pet(self) -> None:
        for iid in self.vpet.stats.inventory:
            it = ITEMS_CATALOG.get(iid)
            if it and it.category in ("food", "drink", "gift"):
                self._use_bag_item(iid)
                return
        self.say("Backpack is empty! Opening BetterBuy shop… 🛒", timeout_s=4, speak_voice=True)
        self._open_betterbuy_shop()

    def pet_cat(self) -> None:
        mood, msg = self.vpet.pet_head()
        _play_sound_cue("purr")
        self._refresh_stats_panel()

        purrs = [
            f"✨ Woody OS online and running smooth! Level {self.vpet.stats.level} active.",
            "⚡ Systems optimized. What would you like to execute?",
            "🐾 Woody here! Ready for any Windows task or question.",
        ]
        self.say(random.choice(purrs), timeout_s=4, speak_voice=True)
        self._show_input()

    def _toggle_sleep(self) -> None:
        if self.is_sleeping:
            self.is_sleeping = False
            self.set_action("idle", loop=True)
            self.say("⚡ Wide awake and energized! Purr!", timeout_s=3, speak_voice=True)
        else:
            self.is_sleeping = True
            self.set_action("sleep", loop=True)
            self.say("Taking a peaceful nap… Zzz", timeout_s=3, is_thought=True)

    # ── Authentic VPet BetterBuy Store Window (Purple Theme) ──────────────────

    def _open_betterbuy_shop(self) -> None:
        top = tk.Toplevel(self.window)
        top.title("🛍️ BetterBuy Item Shop")
        top.geometry("520x520")
        top.configure(bg="#110724")
        top.attributes("-topmost", True)

        hdr = tk.Frame(top, bg=C_PRIMARY, padx=12, pady=10)
        hdr.pack(fill="x")

        tk.Label(
            hdr,
            text="🛍️ BetterBuy Item Shop",
            bg=C_PRIMARY,
            fg="#ffffff",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")

        balance_lbl = tk.Label(
            hdr,
            text=f"🪙 Balance: ${self.vpet.stats.money:,}",
            bg=C_PRIMARY,
            fg=C_GOLD,
            font=("Segoe UI", 11, "bold"),
        )
        balance_lbl.pack(side="right")

        canvas = tk.Canvas(top, bg="#110724", bd=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(top, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#110724")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        scrollbar.pack(side="right", fill="y")

        for item_id, item in ITEMS_CATALOG.items():
            card = tk.Frame(scrollable_frame, bg=C_BG_CARD, padx=10, pady=8, highlightthickness=1, highlightbackground=C_BORDER)
            card.pack(fill="x", pady=4)

            left_f = tk.Frame(card, bg=C_BG_CARD)
            left_f.pack(side="left", fill="x", expand=True)

            tk.Label(
                left_f,
                text=f"{item.icon} {item.name}  —  🪙 ${int(item.price)}",
                bg=C_BG_CARD,
                fg="#f8fafc",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w")

            stats_preview = []
            if item.fullness: stats_preview.append(f"Food+{int(item.fullness)}")
            if item.thirst: stats_preview.append(f"Water+{int(item.thirst)}")
            if item.energy: stats_preview.append(f"Stamina+{int(item.energy)}")
            if item.health: stats_preview.append(f"Health+{int(item.health)}")
            if item.mood: stats_preview.append(f"Mood+{int(item.mood)}")
            if item.exp: stats_preview.append(f"EXP+{item.exp}")

            tk.Label(
                left_f,
                text=f"{item.description} ({', '.join(stats_preview)})",
                bg=C_BG_CARD,
                fg=C_TEXT_MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor="w")

            def _buy(iid=item_id):
                ok, msg = self.vpet.buy_item(iid)
                _play_sound_cue("coin" if ok else "purr")
                balance_lbl.config(text=f"🪙 Balance: ${self.vpet.stats.money:,}")
                self.say(msg, timeout_s=4, speak_voice=ok)
                self._refresh_stats_panel()

            tk.Button(
                card,
                text="Buy",
                command=_buy,
                bg=C_PRIMARY,
                fg="#ffffff",
                activebackground=C_PRIMARY_HOVER,
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                padx=12,
                pady=4,
                cursor="hand2",
            ).pack(side="right")

    # ── Authentic VPet Jobs & Work Window (Purple Theme) ──────────────────────

    def _open_jobs_window(self, category: str = "work") -> None:
        top = tk.Toplevel(self.window)
        title_txt = "💼 Work Center" if category == "work" else "📚 Academy Study Center"
        top.title(title_txt)
        top.geometry("480x440")
        top.configure(bg="#110724")
        top.attributes("-topmost", True)

        hdr = tk.Frame(top, bg=C_PRIMARY, padx=12, pady=10)
        hdr.pack(fill="x")

        tk.Label(
            hdr,
            text=title_txt,
            bg=C_PRIMARY,
            fg="#ffffff",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")

        jobs_frame = tk.Frame(top, bg="#110724", padx=12, pady=10)
        jobs_frame.pack(fill="both", expand=True)

        for job_id, job in JOBS_CATALOG.items():
            if job.category != category:
                continue

            card = tk.Frame(jobs_frame, bg=C_BG_CARD, padx=10, pady=8, highlightthickness=1, highlightbackground=C_BORDER)
            card.pack(fill="x", pady=4)

            left_f = tk.Frame(card, bg=C_BG_CARD)
            left_f.pack(side="left", fill="x", expand=True)

            gold_t = f"🪙 +${job.gold_reward}  " if job.gold_reward > 0 else ""
            tk.Label(
                left_f,
                text=f"{job.name}  ({job.duration_s}s)",
                bg=C_BG_CARD,
                fg="#f8fafc",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")

            tk.Label(
                left_f,
                text=f"Reward: {gold_t}⭐ +{job.exp_reward} EXP  |  Cost: ⚡ -{int(job.energy_cost)}%",
                bg=C_BG_CARD,
                fg=C_TEXT_MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor="w")

            def _start(jid=job_id):
                ok, msg = self.vpet.start_job(jid)
                if ok:
                    act_map = {
                        "coding": "work_coding",
                        "sausage": "work_sausage",
                        "calligraphy": "work_calligraphy",
                        "office": "work_office",
                        "streaming": "work_streaming",
                        "ai_ml": "study",
                        "math": "study_math",
                        "literature": "study_paint",
                    }
                    self.set_action(act_map.get(jid, "work_coding"), loop=True)
                _play_sound_cue("coin" if ok else "purr")
                self.say(msg, timeout_s=5, speak_voice=ok)
                top.destroy()
                self._refresh_stats_panel()

            tk.Button(
                card,
                text="Start",
                command=_start,
                bg=C_PRIMARY,
                fg="#ffffff",
                activebackground=C_PRIMARY_HOVER,
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                padx=12,
                pady=4,
                cursor="hand2",
            ).pack(side="right")

    # ── Voice Synthesis (Pipelined Inworld / Edge Neural Voice) ───────────────

    def start_voice_stream(self) -> asyncio.Queue[str | None]:
        """Start a new sentence queue for pipelined streaming speech with zero delay."""
        self.stop_voice()
        fut = asyncio.run_coroutine_threadsafe(self._create_voice_queue_async(), self._voice_loop)
        q = fut.result(timeout=1.0)
        self._active_voice_queue = q
        return q

    async def _create_voice_queue_async(self) -> asyncio.Queue[str | None]:
        q: asyncio.Queue[str | None] = asyncio.Queue()
        if hasattr(self, "tts") and self.tts:
            asyncio.create_task(self.tts.speak_sentence_stream(q, on_chunk=lambda _: None))
        return q

    def push_voice_sentence(self, sentence: str) -> None:
        """Push a sentence chunk to the active voice stream for immediate synthesis."""
        clean = self.tts._clean_for_speech(sentence) if hasattr(self.tts, "_clean_for_speech") else sentence.strip()
        if clean and clean != "." and self._active_voice_queue is not None:
            self._voice_loop.call_soon_threadsafe(self._active_voice_queue.put_nowait, clean)

    def finish_voice_stream(self) -> None:
        """Signal that the sentence stream is finished."""
        if self._active_voice_queue is not None:
            self._voice_loop.call_soon_threadsafe(self._active_voice_queue.put_nowait, None)

    def stop_voice(self) -> None:
        """Stop any active TTS audio playback immediately (barge-in)."""
        if hasattr(self, "tts") and self.tts:
            self.tts.stop()
        if self._active_voice_queue is not None:
            try:
                self._voice_loop.call_soon_threadsafe(self._active_voice_queue.put_nowait, None)
            except Exception:
                pass
            self._active_voice_queue = None

    def speak_text_fast(self, text: str) -> None:
        """Speak full text using sentence-level pipelining with zero delay."""
        self.stop_voice()
        if not text.strip():
            return
        clauses = self.tts._split_into_sentences(text) if hasattr(self.tts, "_split_into_sentences") else [text]
        self.start_voice_stream()
        for c in clauses:
            self.push_voice_sentence(c)
        self.finish_voice_stream()

    def speak_inworld_cat_voice(self, text: str) -> None:
        """Backward-compatible voice synthesis entry point using fast sentence stream."""
        self.speak_text_fast(text)

    # ── MessageBar Speech Bubble & AI Q&A ─────────────────────────────────────

    def say(self, text: str, timeout_s: float = 7.0, is_thought: bool = False, speak_voice: bool = False) -> None:
        hdr_txt = f"{self.vpet.stats.name} (Thought):" if is_thought else f"{self.vpet.stats.name} (Virtual Pet):"
        self.messagebar_header.config(text=hdr_txt)
        self.messagebar_text.config(text=text.strip())
        self.messagebar_frame.pack(side="top", fill="x", padx=8, pady=2, before=self.pet_label)

        if speak_voice:
            self.set_action("say", loop=False)
            self.speak_text_fast(text)

        if self.bubble_timer:
            self.window.after_cancel(self.bubble_timer)
        if timeout_s > 0:
            self.bubble_timer = self.window.after(int(timeout_s * 1000), self._fade_bubble)

    def _fade_bubble(self) -> None:
        if not self.is_thinking:
            self.messagebar_frame.pack_forget()

    def _show_input(self) -> None:
        self.say("Woody listening. What would you like to execute?", timeout_s=0, speak_voice=False)
        self.input_frame.pack(side="top", fill="x", padx=8, pady=3, before=self.pet_label)
        self.input_entry.delete(0, tk.END)
        self.input_entry.focus_set()

    def _hide_input(self) -> None:
        self.input_frame.pack_forget()
        self.window.focus_set()
        self._fade_bubble()

    def _on_submit_input(self) -> None:
        query = self.input_entry.get().strip()
        if not query:
            self._hide_input()
            return
        self._hide_input()
        self.ask_woody(query)

    def _safe_ui_call(self, fn: Any) -> None:
        """Execute a UI callback on the Tk main thread safely."""
        try:
            if self.window and self.window.winfo_exists():
                self.window.after(0, fn)
        except Exception:
            pass

    def ask_woody(self, prompt: str) -> None:
        """
        Execute user request with full Woody power (LangGraph + all 24 tools + zero-latency speech).
        """
        self.stop_voice()
        self.is_thinking = True
        self.set_action("think", loop=False)
        self.say(f"Thinking: '{prompt[:32]}'…", timeout_s=0, is_thought=True)

        def _worker():
            reply = ""
            self.start_voice_stream()

            # 1. Try FastAPI /api/execute endpoint if backend is running
            try:
                enc = urllib.parse.quote(prompt)
                url = f"{self.server_url}/api/execute?prompt={enc}"
                req = urllib.request.Request(url, headers={"User-Agent": "WoodyPet/1.0"})
                with urllib.request.urlopen(req, timeout=3) as response:
                    sentence_buffer = ""
                    clause_regex = re.compile(r'([.!?\n]+|[,;:—]\s+)')
                    for line_b in response:
                        line = line_b.decode("utf-8", errors="ignore").strip()
                        if line.startswith("data:"):
                            try:
                                payload = json.loads(line[5:].strip())
                                msg_type = payload.get("type", "")
                                if msg_type == "status":
                                    st = payload.get("status") or payload.get("message") or ""
                                    if st:
                                        self._safe_ui_call(lambda s=st: self.say(f"⚡ {s}", timeout_s=0, is_thought=True))
                                elif msg_type in ("response", "chunk"):
                                    txt = payload.get("message") or payload.get("content") or payload.get("text") or ""
                                    if txt:
                                        reply = txt if msg_type == "response" else (reply + txt)
                                        sentence_buffer += txt
                                        while True:
                                            m = clause_regex.search(sentence_buffer)
                                            if not m:
                                                break
                                            sent = sentence_buffer[:m.end()].strip()
                                            sentence_buffer = sentence_buffer[m.end():]
                                            if sent:
                                                self.push_voice_sentence(sent)
                                                self._safe_ui_call(lambda r=reply: (
                                                    self.set_action("say", loop=False),
                                                    self.say(r[:280], timeout_s=0, is_thought=False)
                                                ))
                            except Exception:
                                pass
                    if sentence_buffer.strip():
                        self.push_voice_sentence(sentence_buffer.strip())
            except Exception as ex:
                log.debug("desktop_pet.sse_connect_notice", notice=str(ex))

            # 2. In-process LangGraph agent execution with all 24 tools if SSE didn't return a reply
            if not reply:
                try:
                    from woody.agents.langgraph_graph import graph
                    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
                    if graph:
                        inputs = {"messages": [HumanMessage(content=prompt)]}

                        async def _run_graph():
                            nonlocal reply
                            async for event in graph.astream(inputs, config={"recursion_limit": 6}, stream_mode="updates"):
                                node_name = list(event.keys())[0]
                                node_data = event[node_name]
                                msgs = node_data.get("messages", [])
                                if msgs:
                                    last = msgs[-1]
                                    if isinstance(last, AIMessage):
                                        if last.tool_calls:
                                            tool_names = [tc["name"] for tc in last.tool_calls]
                                            t_info = f"⚡ Woody running: {', '.join(tool_names)}..."
                                            self._safe_ui_call(lambda t=t_info: (
                                                self.set_action("work_coding", loop=True),
                                                self.say(t, timeout_s=0, is_thought=True)
                                            ))
                                        elif last.content:
                                            c_txt = str(last.content).strip()
                                            reply = c_txt
                                            clauses = self.tts._split_into_sentences(c_txt) if hasattr(self.tts, "_split_into_sentences") else [c_txt]
                                            for c in clauses:
                                                self.push_voice_sentence(c)
                                            self._safe_ui_call(lambda r=reply: (
                                                self.set_action("say", loop=False),
                                                self.say(r[:280], timeout_s=0, is_thought=False)
                                            ))
                                    elif isinstance(last, ToolMessage):
                                        tool_name = getattr(last, "name", "tool")
                                        self._safe_ui_call(lambda tn=tool_name: (
                                            self.set_action("work_coding", loop=True),
                                            self.say(f"Executed {tn} successfully.", timeout_s=0, is_thought=True)
                                        ))

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(asyncio.wait_for(_run_graph(), timeout=6.0))
                        finally:
                            loop.close()
                except Exception as e:
                    log.debug("desktop_pet.langgraph_direct_err", error=str(e))

            # 3. Direct Woody Tools router fallback if LangGraph is offline or timed out
            if not reply:
                try:
                    from woody.tools.builtin.system_tools import get_time_date, get_system_stats, get_battery, get_clipboard
                    from woody.tools.builtin.desktop_tools import open_app, take_screenshot, analyze_screen
                    p_low = prompt.lower()
                    if any(w in p_low for w in ("time", "date", "day", "clock")):
                        td = get_time_date()
                        reply = f"It is {td['time']} on {td['date']} ({td['timezone']})."
                    elif any(w in p_low for w in ("battery", "power", "charge")):
                        bat = get_battery()
                        if bat.get("percent") is not None:
                            plug = "plugged in" if bat.get("plugged_in") else "on battery"
                            reply = f"Battery is at {bat['percent']}%, {plug}."
                        else:
                            reply = "No battery detected on this system."
                    elif any(w in p_low for w in ("cpu", "ram", "memory", "stats", "system")):
                        st = get_system_stats()
                        reply = f"CPU is at {st['cpu_percent']}%, RAM at {st['ram_percent']}%, and Disk at {st['disk_percent']}%."
                    elif any(w in p_low for w in ("clipboard", "paste", "copied")):
                        clip = get_clipboard()
                        reply = f"Clipboard content: '{clip['clipboard'][:100]}'" if clip.get("clipboard") else "Clipboard is currently empty."
                    elif "screenshot" in p_low or "capture screen" in p_low:
                        sc = take_screenshot()
                        reply = f"Screenshot captured: {sc.get('path', 'saved')}."
                    elif "open " in p_low or "launch " in p_low:
                        target = p_low.replace("open ", "").replace("launch ", "").strip()
                        res = open_app(target)
                        reply = f"Launched {target} successfully." if res.get("success") else f"Could not open {target}: {res.get('error')}"
                    elif any(w in p_low for w in ("hi", "hello", "hey", "woody")):
                        reply = f"Hello! Woody OS active at Level {self.vpet.stats.level} with ${self.vpet.stats.money:,} Gold. Ready for your command!"
                    else:
                        reply = f"Woody ready! For '{prompt}', I can automate applications, inspect systems, search the web, or manage files."

                    clauses = self.tts._split_into_sentences(reply) if hasattr(self.tts, "_split_into_sentences") else [reply]
                    for c in clauses:
                        self.push_voice_sentence(c)
                except Exception as e:
                    reply = f"Woody online: {prompt}"

            self.finish_voice_stream()

            self.is_thinking = False
            def _apply():
                self.set_action("say", loop=False)
                self.say(reply[:280], timeout_s=12, speak_voice=False)
                self.vpet.add_exp(8)
                self.vpet.stats.money += 2
                self._refresh_stats_panel()

            self._safe_ui_call(_apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _schedule_ambient_thought(self, initial_delay_ms: int = 30000) -> None:
        def _trigger():
            if not self.is_thinking and not self.is_dragging:
                thoughts = [
                    f"Level {self.vpet.stats.level} · Balance: ${self.vpet.stats.money:,} 🪙",
                    "Double click me anytime to chat ✨",
                    "Systems running smooth and cool ⚡",
                    f"It's {time.strftime('%I:%M %p')}. Stay hydrated! 💧",
                    "Hover over me to open VPet Toolbar 🛍️",
                ]
                if self.is_sleeping:
                    thoughts = ["*Zzz... dreaming of stars...*", "*Zzz... purr...*"]

                self.say(random.choice(thoughts), timeout_s=6, is_thought=self.is_sleeping, speak_voice=False)

            next_delay = random.randint(60000, 120000)
            self.ambient_timer = self.window.after(next_delay, _trigger)

        self.ambient_timer = self.window.after(initial_delay_ms, _trigger)

    def _check_system_health(self) -> None:
        try:
            import psutil
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            batt = psutil.sensors_battery()
            batt_str = f" | 🔋 {batt.percent}%" if batt else ""
            msg = f"CPU: {cpu}% | RAM: {mem}%{batt_str}. Systems nominal!"
            self.say(msg, timeout_s=7, speak_voice=True)
        except Exception as e:
            self.say(f"System health check: {e}", timeout_s=4)

    def _open_full_gui(self) -> None:
        try:
            from woody.kernel.kernel import get_kernel
            k = get_kernel()
            if k:
                k.set_mode("normal")
        except Exception:
            pass

        try:
            urllib.request.urlopen(f"{self.server_url}/api/set_mode?mode=normal", timeout=2)
        except Exception:
            pass

        import webbrowser
        webbrowser.open(f"{self.server_url}/")
        self.say("Opened Command Center!", timeout_s=3, speak_voice=True)

    def close(self) -> None:
        self.vpet.save()
        try:
            from woody.kernel.kernel import get_kernel
            k = get_kernel()
            if k:
                k.set_mode("normal")
        except Exception:
            pass

        try:
            urllib.request.urlopen(f"{self.server_url}/api/set_mode?mode=normal", timeout=2)
        except Exception:
            pass

        def _do_destroy():
            self.stop_voice()
            for t_name in ("anim_timer", "ambient_timer", "bubble_timer", "toolbar_leave_timer", "sim_timer", "motion_timer"):
                t = getattr(self, t_name, None)
                if t:
                    try:
                        self.window.after_cancel(t)
                    except Exception:
                        pass
                    setattr(self, t_name, None)
            try:
                self.window.destroy()
            except Exception:
                pass

        # Play shutdown animation sequence before exit
        self.set_action("shutdown", loop=False, on_finish=_do_destroy)
        self.say("See you next time! Farewell~ 👋", timeout_s=2, speak_voice=True)
        self.window.after(2200, _do_destroy)


def run_pet(server_url: str = "http://127.0.0.1:8765") -> None:
    """Launch authentic VPet Desktop Companion in English with Purple Theme."""
    root = tk.Tk()
    app = WoodyAIPet(root=root, server_url=server_url)
    root.mainloop()


if __name__ == "__main__":
    run_pet()
