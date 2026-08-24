"""
Woody AI Desktop Pet — AI-Powered Animated Cat Companion for Windows.

Features:
  - Inworld AI TTS-2 Neural Voice: "community-blcuaurhzmvi" (https://platform.inworld.ai)
  - Seamless transparent, frameless, always-on-top desktop companion
  - Full state machine: Idle, Walk Left, Walk Right, Sleep, Idle-to-Sleep, Sleep-to-Idle, Thinking, Petting, Feeding
  - Mood & Stats System: Energy ⚡, Happiness 💖, Fish Snacks 🐟
  - Interactive Action Bar: Voice input, prompt entry, feed fish, pet cat, system health, sleep/wake
  - Liquid Glass Speech & Thought Bubbles with real-time text and out-loud Inworld voice synthesis
  - Cat sound effects & purrs (Windows native audio feedback)
  - Full Woody AI Kernel connectivity: executes tools, analyzes screen, launches apps, writes emails
"""
from __future__ import annotations

import asyncio
import base64
import ctypes
import json
import os
import random
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from woody.utils.logging import get_logger

log = get_logger(__name__)

# Default GIF asset locations
_MODULE_DIR = Path(__file__).parent
_ROOT_DIR = _MODULE_DIR.parent.parent
GIF_DIR = _ROOT_DIR / "gifs"
if not GIF_DIR.exists():
    GIF_DIR = _MODULE_DIR / "resources" / "gifs"

# Voice identifiers
PET_VOICE_INWORLD = "community-blcuaurhzmvi"   # Custom Cat/Pet Voice from platform.inworld.ai
NORMAL_VOICE_DEFAULT = "Avery"


def _play_sound_cue(cue_type: str = "purr") -> None:
    """Play subtle Windows audio feedback cues."""
    def _worker():
        try:
            import winsound
            if cue_type == "purr":
                for freq in (420, 480, 540, 600):
                    winsound.Beep(freq, 40)
            elif cue_type == "meow":
                winsound.Beep(650, 80)
                winsound.Beep(880, 140)
                winsound.Beep(780, 90)
            elif cue_type == "feed":
                winsound.Beep(520, 60)
                winsound.Beep(680, 80)
                winsound.Beep(840, 100)
            elif cue_type == "chime":
                winsound.Beep(880, 70)
                winsound.Beep(1100, 90)
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()


class WoodyAIPet:
    """
    Interactive Desktop AI Cat Companion powered by Inworld AI voice 'community-blcuaurhzmvi'.
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

        # Inworld API Key from environment or .env
        self.inworld_api_key = os.getenv("INWORLD_API_KEY", "").strip()
        if not self.inworld_api_key:
            env_file = _ROOT_DIR / ".env"
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("INWORLD_API_KEY="):
                            self.inworld_api_key = line.split("=", 1)[1].strip().strip('"\'')
                except Exception:
                    pass

        # Screen dimensions
        self.screen_width = self.window.winfo_screenwidth()
        self.screen_height = self.window.winfo_screenheight()

        # Position & motion
        self.pet_size = 100
        self.x = random.randint(200, max(250, self.screen_width - 320))
        self.floor_y = self.screen_height - 180  # Sits above Windows taskbar
        self.y = self.floor_y
        self.walk_speed = 3

        # State machine variables
        self.cycle = 0
        self.check = 0  # 0: idle, 1: idle_to_sleep, 2: sleep, 3: sleep_to_idle, 4: walk_left, 5: walk_right
        self.event_number = random.choice([1, 2, 3, 4])
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.is_thinking = False
        self.is_speaking_voice = False
        self.show_dock = False

        # Pet Stats & Mood
        self.energy = 100
        self.happiness = 100
        self.fish_snacks = 5

        # Weighted probabilities for spontaneous motion
        self.idle_num = [1, 2, 3, 4]
        self.walk_left = [6, 7]
        self.walk_right = [8, 9]
        self.sleep_num = [10, 11, 12, 13, 15]

        self.bubble_timer: Any | None = None
        self.ambient_timer: Any | None = None

        # Build window & load assets
        self._setup_window()
        self._load_animations()
        self._build_ui()
        self._bind_events()

        # Start autonomous AI personality thoughts & animation loop
        self.say("🐾 Meow! I'm Woody (Cat Mode). Voice: community-blcuaurhzmvi ✨", timeout_s=6, speak_voice=True)
        self._schedule_ambient_thought(initial_delay_ms=12000)
        self.window.after(100, self._event_loop)

    def _setup_window(self) -> None:
        """Configure Tkinter window for transparent, always-on-top frameless floating."""
        self.window.overrideredirect(True)
        self.window.wm_attributes("-topmost", True)
        self.window.config(bg="black")
        self.window.wm_attributes("-transparentcolor", "black")
        self.window.geometry(f"320x240+{self.x-110}+{self.y-120}")

    def _load_animations(self) -> None:
        """Load and extract all GIF action frames."""
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
            "walk_left": ["walk_positive.gif", "1_wKYgYE_uaPVd0-QFantclA.gif"],
            "walk_right": ["walk_negative.gif", "1_6eBKCdbUsBdJJQumlWndww.gif"],
        }

        def _find_file(keys: list[str]) -> Path | None:
            for k in keys:
                p = GIF_DIR / k
                if p.exists():
                    return p
            return None

        def _load_frames(keys: list[str], count_hint: int) -> list[tk.PhotoImage]:
            path = _find_file(keys)
            frames = []
            if path and path.exists():
                for i in range(count_hint + 5):
                    try:
                        f = tk.PhotoImage(file=str(path), format=f"gif -index {i}")
                        frames.append(f)
                    except Exception:
                        break
            return frames

        self.frames_idle = _load_frames(gif_map["idle"], 5)
        self.frames_idle_to_sleep = _load_frames(gif_map["idle_to_sleep"], 8)
        self.frames_sleep = _load_frames(gif_map["sleep"], 3)
        self.frames_sleep_to_idle = _load_frames(gif_map["sleep_to_idle"], 8)
        self.frames_walk_left = _load_frames(gif_map["walk_left"], 8)
        self.frames_walk_right = _load_frames(gif_map["walk_right"], 8)

    def _build_ui(self) -> None:
        """Create speech bubble, interactive action dock, stats pill, and cat sprite."""
        # 1. Top Mood & Stats Pill (Energy, Happiness, Fish count, Voice badge)
        self.stats_frame = tk.Frame(self.window, bg="black")
        self.stats_frame.pack(side="top", fill="x", padx=14, pady=0)

        self.stats_label = tk.Label(
            self.stats_frame,
            text=f"⚡ {self.energy}%  💖 {self.happiness}%  🐟 x{self.fish_snacks}  🎙️ Inworld Cat Voice",
            bg="#111122",
            fg="#a5b4fc",
            font=("Segoe UI", 7, "bold"),
            padx=6,
            pady=2,
            bd=0,
            highlightthickness=1,
            highlightbackground="#4f46e5",
        )
        self.stats_label.pack(fill="x")

        # 2. Speech & Thought Bubble (Glassmorphic look)
        self.bubble_frame = tk.Frame(self.window, bg="black")
        self.bubble_frame.pack(side="top", fill="x", padx=10, pady=2)

        self.bubble_label = tk.Label(
            self.bubble_frame,
            text="🐾 Purr… I'm listening!",
            bg="#16162a",
            fg="#f1f5f9",
            font=("Segoe UI", 8, "bold"),
            wraplength=280,
            justify="center",
            padx=8,
            pady=5,
            bd=0,
            highlightthickness=1,
            highlightbackground="#6366f1",
        )
        self.bubble_label.pack(fill="x")

        # 3. Interactive Quick Action Dock (Toolbar)
        self.dock_frame = tk.Frame(self.window, bg="black")
        self.dock_frame.pack(side="top", fill="x", padx=10, pady=2)

        btn_style = {
            "bg": "#1e1b4b",
            "fg": "#e0e7ff",
            "activebackground": "#4338ca",
            "activeforeground": "#ffffff",
            "font": ("Segoe UI", 7, "bold"),
            "bd": 0,
            "padx": 4,
            "pady": 2,
            "relief": "flat",
            "cursor": "hand2",
        }

        self.btn_ask = tk.Button(self.dock_frame, text="💬 Ask", command=self._show_input, **btn_style)
        self.btn_ask.pack(side="left", padx=1)

        self.btn_voice = tk.Button(self.dock_frame, text="🎤 Voice", command=self._trigger_voice, **btn_style)
        self.btn_voice.pack(side="left", padx=1)

        self.btn_feed = tk.Button(self.dock_frame, text="🐟 Feed", command=self.feed_pet, **btn_style)
        self.btn_feed.pack(side="left", padx=1)

        self.btn_pet = tk.Button(self.dock_frame, text="✨ Pet", command=self.pet_cat, **btn_style)
        self.btn_pet.pack(side="left", padx=1)

        self.btn_sleep = tk.Button(self.dock_frame, text="💤 Nap", command=self._toggle_sleep, **btn_style)
        self.btn_sleep.pack(side="left", padx=1)

        self.btn_gui = tk.Button(self.dock_frame, text="🖥️ UI", command=self._open_full_gui, **btn_style)
        self.btn_gui.pack(side="left", padx=1)

        self.btn_close = tk.Button(self.dock_frame, text="✕", command=self.close, **btn_style)
        self.btn_close.pack(side="left", padx=1)

        # 4. Quick Input Field (Hidden by default, toggled via Ask or double-click)
        self.input_frame = tk.Frame(self.window, bg="black")
        self.input_entry = tk.Entry(
            self.input_frame,
            bg="#18182f",
            fg="#ffffff",
            insertbackground="#a78bfa",
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#8b5cf6",
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=4, pady=2)
        self.input_entry.bind("<Return>", lambda e: self._on_submit_input())
        self.input_entry.bind("<Escape>", lambda e: self._hide_input())

        # 5. Main Pet Sprite Label
        initial_img = self.frames_idle[0] if self.frames_idle else None
        self.pet_label = tk.Label(
            self.window,
            image=initial_img,
            bd=0,
            bg="black",
            cursor="hand2",
        )
        self.pet_label.pack(side="bottom", pady=2)

        # Right-click context menu
        self.menu = tk.Menu(
            self.window,
            tearoff=0,
            bg="#18182b",
            fg="#ffffff",
            activebackground="#6366f1",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
        )
        self.menu.add_command(label="💬 Ask Woody (Double Click)", command=self._show_input)
        self.menu.add_command(label="🎤 Speak (Voice Input)", command=self._trigger_voice)
        self.menu.add_command(label="🐟 Feed Fish Snack", command=self.feed_pet)
        self.menu.add_command(label="✨ Pet Cat (Purr)", command=self.pet_cat)
        self.menu.add_separator()
        self.menu.add_command(label="📊 Check System Health (CPU/RAM)", command=self._check_system_health)
        self.menu.add_command(label="⚡ Wake Up / Stand Up", command=self._wake_up)
        self.menu.add_command(label="💤 Take a Nap", command=self._go_to_sleep)
        self.menu.add_separator()
        self.menu.add_command(label="🎙️ Voice: Inworld (community-blcuaurhzmvi)", command=lambda: self.say("Voice active: Inworld Cat (community-blcuaurhzmvi)", speak_voice=True))
        self.menu.add_command(label="🖥️ Switch to Normal Mode & Open UI", command=self._open_full_gui)
        self.menu.add_command(label="❌ Exit Pet Mode", command=self.close)

    def _bind_events(self) -> None:
        """Bind mouse dragging, double-clicking, and right-clicks."""
        self.pet_label.bind("<Button-1>", self._on_drag_start)
        self.pet_label.bind("<B1-Motion>", self._on_drag_motion)
        self.pet_label.bind("<ButtonRelease-1>", self._on_drag_end)
        self.pet_label.bind("<Double-Button-1>", lambda e: self._show_input())
        self.pet_label.bind("<Button-3>", self._show_context_menu)

        # Clicking the bubble or stats bar prompts interaction
        self.bubble_label.bind("<Button-1>", lambda e: self.pet_cat())
        self.stats_label.bind("<Button-1>", lambda e: self._toggle_dock())

    def _update_stats_display(self) -> None:
        """Refresh energy, happiness, and snack counters."""
        self.stats_label.config(
            text=f"⚡ {self.energy}%  💖 {self.happiness}%  🐟 x{self.fish_snacks}  🎙️ {self.pet_voice[:14]}…"
        )

    def _toggle_dock(self) -> None:
        if self.show_dock:
            self.dock_frame.pack_forget()
            self.show_dock = False
        else:
            self.dock_frame.pack(side="top", fill="x", padx=10, pady=2)
            self.show_dock = True

    # ── State Machine & Frame Animation Loop ──────────────────────────────────

    def _gif_work(self, cycle: int, frames: list[tk.PhotoImage], first_num: int, last_num: int) -> tuple[int, int]:
        if not frames:
            return 0, random.randint(first_num, last_num)
        if cycle < len(frames) - 1:
            cycle += 1
        else:
            cycle = 0
            self.event_number = random.randint(first_num, last_num)
        return cycle, self.event_number

    def _event_loop(self) -> None:
        if self.is_dragging:
            self.window.after(100, self._event_loop)
            return

        # Idle
        if self.event_number in self.idle_num:
            self.check = 0
            delay = 350
        # Idle to Sleep
        elif self.event_number == 5:
            self.check = 1
            delay = 120
        # Walk Left
        elif self.event_number in self.walk_left:
            self.check = 4
            delay = 100
            # Walking burns tiny energy
            self.energy = max(10, self.energy - 1)
            self._update_stats_display()
        # Walk Right
        elif self.event_number in self.walk_right:
            self.check = 5
            delay = 100
            self.energy = max(10, self.energy - 1)
            self._update_stats_display()
        # Sleeping
        elif self.event_number in self.sleep_num:
            self.check = 2
            delay = 800
            # Sleeping recharges energy!
            self.energy = min(100, self.energy + 3)
            self._update_stats_display()
        # Sleep to Idle (Wake up)
        elif self.event_number == 14:
            self.check = 3
            delay = 120
        else:
            self.check = 0
            delay = 300

        self.window.after(delay, self._update_frame)

    def _update_frame(self) -> None:
        if self.is_dragging:
            self.window.after(100, self._event_loop)
            return

        frame = None

        # 0: Idle
        if self.check == 0:
            if self.frames_idle:
                frame = self.frames_idle[self.cycle % len(self.frames_idle)]
            self.cycle, self.event_number = self._gif_work(self.cycle, self.frames_idle, 1, 9)

        # 1: Idle to sleep
        elif self.check == 1:
            if self.frames_idle_to_sleep:
                frame = self.frames_idle_to_sleep[self.cycle % len(self.frames_idle_to_sleep)]
            self.cycle, self.event_number = self._gif_work(self.cycle, self.frames_idle_to_sleep, 10, 10)

        # 2: Sleep
        elif self.check == 2:
            if self.frames_sleep:
                frame = self.frames_sleep[self.cycle % len(self.frames_sleep)]
            self.cycle, self.event_number = self._gif_work(self.cycle, self.frames_sleep, 10, 15)

        # 3: Sleep to idle
        elif self.check == 3:
            if self.frames_sleep_to_idle:
                frame = self.frames_sleep_to_idle[self.cycle % len(self.frames_sleep_to_idle)]
            self.cycle, self.event_number = self._gif_work(self.cycle, self.frames_sleep_to_idle, 1, 1)

        # 4: Walk towards left
        elif self.check == 4:
            if self.frames_walk_left:
                frame = self.frames_walk_left[self.cycle % len(self.frames_walk_left)]
            self.cycle, self.event_number = self._gif_work(self.cycle, self.frames_walk_left, 1, 9)
            self.x -= self.walk_speed
            if self.x < 20:
                self.x = 20
                self.event_number = 8  # Turn and walk right

        # 5: Walk towards right
        elif self.check == 5:
            if self.frames_walk_right:
                frame = self.frames_walk_right[self.cycle % len(self.frames_walk_right)]
            self.cycle, self.event_number = self._gif_work(self.cycle, self.frames_walk_right, 1, 9)
            self.x += self.walk_speed
            if self.x > self.screen_width - 180:
                self.x = self.screen_width - 180
                self.event_number = 6  # Turn and walk left

        if frame:
            self.pet_label.configure(image=frame)

        self.window.geometry(f"320x240+{self.x - 110}+{self.y - 120}")
        self.window.after(1, self._event_loop)

    # ── Mouse Interaction & Dragging ──────────────────────────────────────────

    def _on_drag_start(self, event: tk.Event) -> None:
        self.is_dragging = True
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        _play_sound_cue("meow")
        self.say("🐾 Meow! Put me down gently!", timeout_s=2)

    def _on_drag_motion(self, event: tk.Event) -> None:
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        self.x += dx
        self.y += dy
        self.window.geometry(f"320x240+{self.x - 110}+{self.y - 120}")

    def _on_drag_end(self, event: tk.Event) -> None:
        self.is_dragging = False
        if self.y > self.screen_height - 220:
            self.y = self.floor_y
        self.event_number = 1  # Land in idle
        _play_sound_cue("purr")
        self.say("🐾 Landed safely on all four paws!", timeout_s=3)

    def _show_context_menu(self, event: tk.Event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ── Feeding & Petting Interactive Actions ──────────────────────────────────

    def feed_pet(self) -> None:
        """Feed a fish snack to Woody."""
        self._wake_up()
        if self.fish_snacks <= 0:
            self.fish_snacks = 5
            self.say("🐾 Caught 5 fresh fish snacks from the web! 🐟", timeout_s=4, speak_voice=True)
            self._update_stats_display()
            return

        self.fish_snacks -= 1
        self.energy = min(100, self.energy + 25)
        self.happiness = min(100, self.happiness + 20)
        self._update_stats_display()
        _play_sound_cue("feed")

        phrases = [
            "🐟 Nom nom nom! That fish was delicious! Purr!",
            "🐟 Yummy snack! Energy recharged to maximum!",
            "🐟 Purrfect! My favorite treat! Thank you!",
        ]
        self.say(random.choice(phrases), timeout_s=5, speak_voice=True)

    def pet_cat(self) -> None:
        """Pet Woody the cat."""
        self._wake_up()
        self.happiness = min(100, self.happiness + 15)
        self._update_stats_display()
        _play_sound_cue("purr")

        purrs = [
            "✨ *Purrrrrrr*... You're the best companion!",
            "💖 Purr... that feels amazing behind my ears!",
            "🐾 *Happy purrs*... Woody is pleased! Meow!",
            "✨ *Purr*... Ready to conquer some tasks together!",
        ]
        self.say(random.choice(purrs), timeout_s=4, speak_voice=True)

    def _toggle_sleep(self) -> None:
        if self.check == 2:
            self._wake_up()
            self.say("⚡ Wide awake and energized! Meow!", timeout_s=3, speak_voice=True)
        else:
            self._go_to_sleep()

    # ── Voice Synthesis (Inworld community-blcuaurhzmvi) ──────────────────────

    def speak_inworld_cat_voice(self, text: str) -> None:
        """Synthesize and play speech using Inworld custom cat voice 'community-blcuaurhzmvi'."""
        clean_text = text.replace("🐾", "").replace("💭", "").replace("🐟", "").replace("⚡", "").replace("💖", "").replace("✨", "").strip()
        if not clean_text or not self.inworld_api_key:
            return

        def _voice_thread():
            try:
                headers = {
                    "Authorization": f"Basic {self.inworld_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "text": clean_text,
                    "voiceId": self.pet_voice,
                    "modelId": "inworld-tts-2",
                    "audioConfig": {"speakingRate": 1.05},
                    "deliveryMode": "CREATIVE",
                    "language": "AUTO",
                }
                req = urllib.request.Request(
                    "https://api.inworld.ai/tts/v1/voice",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    if response.status == 200:
                        res_data = json.loads(response.read().decode("utf-8"))
                        b64 = res_data.get("audioContent")
                        if b64:
                            audio_bytes = base64.b64decode(b64)
                            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                                f.write(audio_bytes)
                                temp_path = f.name
                            
                            # Native Windows MCI audio playback
                            alias = f"cat_voice_{int(time.time()*1000)}"
                            ctypes.windll.winmm.mciSendStringW(f'open "{temp_path}" type mpegvideo alias {alias}', None, 0, 0)
                            ctypes.windll.winmm.mciSendStringW(f'play {alias} wait', None, 0, 0)
                            ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, 0)
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
            except Exception as e:
                log.debug("desktop_pet.inworld_voice_err", error=str(e))

        threading.Thread(target=_voice_thread, daemon=True).start()

    # ── AI Brain & Speech Bubble Interactions ─────────────────────────────────

    def say(self, text: str, timeout_s: float = 7.0, is_thought: bool = False, speak_voice: bool = False) -> None:
        """Display a speech or thought bubble and optionally speak with Inworld Cat voice."""
        prefix = "💭 " if is_thought else "🐾 "
        clean_text = text.strip()
        if not clean_text.startswith("🐾") and not clean_text.startswith("💭"):
            clean_text = prefix + clean_text

        self.bubble_label.config(text=clean_text)
        self.bubble_frame.pack(side="top", fill="x", padx=10, pady=2)

        if speak_voice:
            self.speak_inworld_cat_voice(text)

        if self.bubble_timer:
            self.window.after_cancel(self.bubble_timer)
        if timeout_s > 0:
            self.bubble_timer = self.window.after(int(timeout_s * 1000), self._fade_bubble)

    def _fade_bubble(self) -> None:
        if not self.is_thinking:
            self.bubble_frame.pack_forget()

    def _show_input(self) -> None:
        self._wake_up()
        self.say("Meow! What do you need help with?", timeout_s=0, speak_voice=True)
        self.input_frame.pack(side="top", fill="x", padx=10, pady=3)
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

    def ask_woody(self, prompt: str) -> None:
        """Send a command to Woody AI Kernel or FastAPI server and speak the reply."""
        self._wake_up()
        self.is_thinking = True
        self.say(f"🐾 Thinking: '{prompt}'…", timeout_s=0)

        def _worker():
            reply = ""
            try:
                from woody.kernel.kernel import get_kernel
                kernel = get_kernel()
                if kernel:
                    # Switch kernel TTS voice to cat voice during pet mode
                    kernel.set_mode("pet")
                    loop = getattr(kernel, "_loop", None) or asyncio.new_event_loop()
                    reply = loop.run_until_complete(kernel.process_request(prompt))
            except Exception as e:
                log.debug("desktop_pet.kernel_call_fallback", error=str(e))

            if not reply:
                try:
                    enc = urllib.parse.quote(prompt)
                    url = f"{self.server_url}/api/execute?prompt={enc}"
                    req = urllib.request.Request(url, headers={"User-Agent": "WoodyPet/1.0"})
                    with urllib.request.urlopen(req, timeout=12) as response:
                        lines = response.read().decode("utf-8").splitlines()
                        for line in lines:
                            if line.startswith("data:"):
                                try:
                                    payload = json.loads(line[5:].strip())
                                    if payload.get("type") in ("chunk", "done", "token"):
                                        reply += payload.get("content", "")
                                    elif "text" in payload:
                                        reply = payload["text"]
                                except Exception:
                                    pass
                except Exception as ex:
                    log.debug("desktop_pet.sse_fallback", error=str(ex))

            if not reply:
                p_low = prompt.lower()
                if "time" in p_low:
                    reply = time.strftime("It is %I:%M %p on %A! Purr.")
                elif "cpu" in p_low or "ram" in p_low or "stat" in p_low:
                    try:
                        import psutil
                        reply = f"Meow! CPU is at {psutil.cpu_percent()}% and RAM is at {psutil.virtual_memory().percent}%."
                    except Exception:
                        reply = "Systems are running smoothly and purring nicely!"
                elif "hi" in p_low or "hello" in p_low:
                    reply = "Hello! I'm your desktop cat assistant. Meow!"
                else:
                    reply = f"Meow! Working on '{prompt}' right now!"

            def _apply():
                self.is_thinking = False
                self.say(reply[:200], timeout_s=10, speak_voice=True)

            self.window.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _schedule_ambient_thought(self, initial_delay_ms: int = 15000) -> None:
        """Autonomous cat AI thoughts that fire periodically."""
        def _trigger():
            if not self.is_thinking and not self.is_dragging:
                thoughts = [
                    "All systems nominal! Double click me to chat 🐾",
                    "CPU is running cool and purring smoothly ⚡",
                    f"It's {time.strftime('%I:%M %p')}. Stay hydrated and stretch!",
                    "Did you know I can compose emails and launch apps for you?",
                    "Watching your desktop like a good feline companion ✨",
                    "Feed me a fish snack or pet me if you're taking a break! 🐟",
                ]
                if self.check == 2:
                    thoughts = ["*Zzz... dreaming of laser pointers...*", "*Zzz... purr...*", "*Zzz... clean code...*"]

                is_sleep = (self.check == 2)
                self.say(random.choice(thoughts), timeout_s=6, is_thought=is_sleep, speak_voice=(not is_sleep))

            next_delay = random.randint(40000, 75000)
            self.ambient_timer = self.window.after(next_delay, _trigger)

        self.ambient_timer = self.window.after(initial_delay_ms, _trigger)

    def _trigger_voice(self) -> None:
        self._wake_up()
        _play_sound_cue("meow")
        self.say("🎤 Listening… meow what you need!", timeout_s=4, speak_voice=True)
        try:
            from woody.kernel.kernel import get_kernel
            k = get_kernel()
            if k:
                k.set_mode("pet")
                k._handle_wake_word()
        except Exception:
            pass

    def _check_system_health(self) -> None:
        try:
            import psutil
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            batt = psutil.sensors_battery()
            batt_str = f" | 🔋 {batt.percent}%" if batt else ""
            msg = f"CPU: {cpu}% | RAM: {mem}%{batt_str}. Purring along smoothly!"
            self.say(msg, timeout_s=7, speak_voice=True)
        except Exception as e:
            self.say(f"System health check: {e}", timeout_s=4)

    def _wake_up(self) -> None:
        self.event_number = 14
        self.check = 3
        self.cycle = 0

    def _go_to_sleep(self) -> None:
        self.event_number = 5
        self.check = 1
        self.cycle = 0
        self.say("Taking a quick cat nap… Zzz", timeout_s=3, is_thought=True)

    def _open_full_gui(self) -> None:
        """Restore normal voice mode and open full web overlay."""
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
        self.say("Restored normal voice mode & opened Command Center!", timeout_s=3)

    def close(self) -> None:
        """Restore normal voice mode and cleanly exit pet."""
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

        if self.ambient_timer:
            self.window.after_cancel(self.ambient_timer)
        if self.bubble_timer:
            self.window.after_cancel(self.bubble_timer)
        self.window.destroy()


def run_pet(server_url: str = "http://127.0.0.1:8765") -> None:
    """Launch standalone Desktop AI Pet with Inworld cat voice."""
    root = tk.Tk()
    app = WoodyAIPet(root=root, server_url=server_url)
    root.mainloop()


if __name__ == "__main__":
    run_pet()
