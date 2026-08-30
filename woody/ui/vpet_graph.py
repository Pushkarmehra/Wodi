"""
VPet Native Graph Animation Engine for Woody AI Operating System.

Indexes and plays all 6,181 frames across 25 official VPet animation categories:
  • Default: Nomal, Happy, PoorCondition, Ill
  • IDEL: Meow, MeowLook, Bubbles, Tennis, Squat, Yawning, Aside, Happy_Like520, Boring
  • Music: Headphone dancing & listening sequences (354 frames)
  • Gift: Opening gift boxes & joy reactions (157 frames)
  • BDay: Birthday fanfare & celebration (53 frames)
  • StartUP & Shutdown: Welcome & farewell sequences (290 frames)
  • Touch_Head & Touch_Body: Petting & tickle sequences (169 frames)
  • Eat & Drink: Food snacks & drink bottles (217 frames)
  • Pinch & Raise: Dragging & hanging in air (283 frames)
  • Sleep: Resting in bed (57 frames)
  • LevelUP: Milestone fireworks & celebration (82 frames)
  • Say & Think: Speaking & pondering gestures (262 frames)
  • MOVE: Desktop traversal (climb, crawl, walk, fall - 534 frames)
  • WORK: 13 work/study animations (FixMenu, GrilledSausage, Calligraphy,
          WorkONE, WorkTWO, WorkClean, Study, StudyPaint, StudyTWO, PlayONE, PlayWater, RopeSkipping) (2,214 frames)
"""
from __future__ import annotations

import os
import re
import random
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Any
from PIL import Image, ImageTk

from woody.utils.logging import get_logger

log = get_logger(__name__)

# Paths
_MODULE_DIR = Path(__file__).parent
_ROOT_DIR = _MODULE_DIR.parent.parent
VPET_VUP_DIR = _ROOT_DIR / "vpet" / "VPet-main" / "VPet-Simulator.Windows" / "mod" / "0000_core" / "pet" / "vup"
FALLBACK_GIF_DIR = _ROOT_DIR / "gifs"


class VPetGraphEngine:
    """
    Complete VPet animation player supporting all 6,180+ native frames across all 25 categories.
    """

    def __init__(self, target_size: tuple[int, int] = (220, 220), master: tk.Misc | None = None) -> None:
        self.target_size = target_size
        self.master = master
        self.vup_path = VPET_VUP_DIR
        self._cache: dict[str, list[tuple[ImageTk.PhotoImage, int]]] = {}

        # Comprehensive directory mapping for all 25 categories & sub-actions
        self.action_paths: dict[str, list[str]] = {
            # ── Default Idles ──
            "idle": ["Default/Nomal/1", "Default/Nomal/A", "Default/Nomal"],
            "idle_happy": ["Default/Happy/1", "Default/Happy/A", "Default/Happy"],
            "idle_poor": ["Default/PoorCondition/1", "Default/PoorCondition"],
            "idle_ill": ["Default/Ill/1", "Default/Ill"],

            # ── IDEL Expressions & Activities (849 frames) ──
            "idle_meow": ["IDEL/Meow/Happy", "IDEL/Meow/Nomal", "IDEL/Meow"],
            "idle_meowlook": ["IDEL/meowlook/Happy", "IDEL/meowlook/Nomal", "IDEL/meowlook"],
            "idle_bubbles": ["IDEL/Bubbles/Happy", "IDEL/Bubbles/Nomal", "IDEL/Bubbles"],
            "idle_tennis": ["IDEL/Tennis/Happy", "IDEL/Tennis/Nomal", "IDEL/Tennis"],
            "idle_squat": ["IDEL/Squat/Happy", "IDEL/Squat/Nomal", "IDEL/Squat"],
            "idle_yawning": ["IDEL/yawning/Happy", "IDEL/yawning/Nomal", "IDEL/yawning"],
            "idle_aside": ["IDEL/aside/Happy", "IDEL/aside/Nomal", "IDEL/aside"],
            "idle_like520": ["IDEL/happy_like520/Happy", "IDEL/happy_like520/Nomal", "IDEL/happy_like520"],
            "idle_boring": ["IDEL/Boring/Happy", "IDEL/Boring/Nomal", "IDEL/Boring"],

            # ── Special Actions ──
            "music": ["Music/Single", "Music/B", "Music/C", "Music/A"],
            "gift": ["Gift/Happy", "Gift/Nomal", "Gift/PoorCondition"],
            "bday": ["BDay/B", "BDay/A", "BDay/C"],
            "startup": ["StartUP/Happy", "StartUP/Nomal", "StartUP/Happy_1"],
            "shutdown": ["Shutdown/2", "Shutdown/Happy_1", "Shutdown/Nomal_1"],

            # ── Touch & Drag ──
            "touch_head": ["Touch_Head/Happy/A", "Touch_Head/Happy", "Touch_Head/A_Nomal/A"],
            "touch_body": ["Touch_Body/A_Happy", "Touch_Body/A_Nomal/A", "Touch_Body/B_Happy"],
            "pinch": ["Pinch/Nomal", "Pinch/Happy", "Pinch/PoorCondition"],
            "raise": ["Raise/Happy", "Raise/Nomal", "Raise/PoorCondition"],

            # ── Vitals & Recovery ──
            "sleep": ["Sleep/A_Nomal", "Sleep/A_Happy", "Sleep/B_Nomal"],
            "eat": ["Eat/Nomal", "Eat/Happy"],
            "drink": ["Drink/Nomal", "Drink/Happy"],
            "levelup": ["LevelUP/Happy", "LevelUP/Nomal"],

            # ── Communication ──
            "say": ["Say/Shining", "Say/Self", "Say/Serious", "Say/Shy", "Say/Nomal"],
            "think": ["Think/Happy", "Think/Nomal", "Think/PoorCondition"],

            # ── Movement & Traversal ──
            "move_right": ["MOVE/crawl.right/A_Happy", "MOVE/crawl.right/A_Nomal", "MOVE/crawl.right", "MOVE/walk.right"],
            "move_left": ["MOVE/crawl.left/A_Happy", "MOVE/crawl.left/A_Nomal", "MOVE/crawl.left", "MOVE/walk.left"],
            "climb_left": ["MOVE/climb.left"],
            "climb_right": ["MOVE/climb.right"],

            # ── Work & Study Jobs (2,214 frames) ──
            "work_coding": ["WORK/FixMenu/Nomal", "WORK/FixMenu/Happy"],
            "work_sausage": ["WORK/GrilledSausage/Nomal", "WORK/GrilledSausage/Happy"],
            "work_calligraphy": ["WORK/Calligraphy/Nomal", "WORK/Calligraphy/Happy"],
            "work_clean": ["WORK/WorkClean/Nomal", "WORK/WorkClean/Happy"],
            "work_office": ["WORK/WorkONE/Nomal", "WORK/WorkONE/Happy"],
            "work_streaming": ["WORK/WorkTWO/Nomal", "WORK/WorkTWO/Happy"],
            "work_game": ["WORK/PlayONE/Nomal", "WORK/PlayONE/Happy"],
            "work_water": ["WORK/PlayWater/Happy", "WORK/PlayWater/Nomal"],
            "work_rope": ["WORK/RopeSkipping/Happy", "WORK/RopeSkipping/Nomal"],
            "work_remove": ["WORK/RemoveObject/Nomal", "WORK/RemoveObject/Happy"],
            "study": ["WORK/Study/Happy", "WORK/Study/Nomal"],
            "study_math": ["WORK/StudyTWO/Happy", "WORK/StudyTWO/Nomal"],
            "study_paint": ["WORK/StudyPaint/Happy", "WORK/StudyPaint/Nomal"],
        }

    def _process_image_frame(self, file_path: Path) -> ImageTk.PhotoImage:
        """Process PNG into transparent PhotoImage with clean alpha thresholding for Windows."""
        im = Image.open(file_path).convert("RGBA")
        im.thumbnail(self.target_size, Image.Resampling.LANCZOS)
        
        # Center in canvas
        canvas = Image.new("RGBA", self.target_size, (0, 0, 0, 0))
        ox = (self.target_size[0] - im.width) // 2
        oy = self.target_size[1] - im.height
        canvas.paste(im, (ox, oy), im)

        # Alpha thresholding for crisp transparent rendering
        r, g, b, a = canvas.split()
        mask = a.point(lambda p: 255 if p > 35 else 0)
        bg = Image.new("RGB", self.target_size, (0, 0, 0))
        bg.paste(canvas, mask=mask)
        return ImageTk.PhotoImage(bg, master=self.master)

    def load_sequence(self, action_name: str) -> list[tuple[ImageTk.PhotoImage, int]]:
        """Load and cache a native animation sequence from VPet vup directory."""
        if action_name in self._cache:
            try:
                if self._cache[action_name]:
                    self._cache[action_name][0][0].width()
                return self._cache[action_name]
            except Exception:
                self._cache.clear()

        paths = self.action_paths.get(action_name, [action_name])
        frames: list[tuple[ImageTk.PhotoImage, int]] = []

        if self.vup_path.exists():
            for rel in paths:
                act_dir = self.vup_path / rel
                if act_dir.exists():
                    pngs = sorted(list(act_dir.rglob("*.png")))
                    if pngs:
                        for p in pngs:
                            m = re.search(r"_(\d+)_(\d+)\.png", p.name)
                            dur_ms = int(m.group(2)) if m else 150
                            dur_ms = max(40, min(800, dur_ms))  # Smooth frame delay
                            try:
                                photo = self._process_image_frame(p)
                                frames.append((photo, dur_ms))
                            except Exception as e:
                                log.debug("vpet_graph.frame_err", file=str(p), error=str(e))
                        if frames:
                            break

        # Fallback to compiled GIF frames if VPet raw directory was moved
        if not frames:
            gif_name = "idle.gif" if "idle" in action_name else "walk_positive.gif" if "right" in action_name else "walk_negative.gif" if "left" in action_name else "sleep.gif"
            gif_path = FALLBACK_GIF_DIR / gif_name
            if gif_path.exists():
                for idx in range(12):
                    try:
                        tk_img = tk.PhotoImage(file=str(gif_path), format=f"gif -index {idx}")
                        frames.append((tk_img, 150))
                    except Exception:
                        break

        self._cache[action_name] = frames
        return frames

    def get_random_idle_action(self) -> str:
        """Return a randomized idle variation from official VPet IDEL categories."""
        idles = [
            "idle",
            "idle_happy",
            "idle_meow",
            "idle_meowlook",
            "idle_bubbles",
            "idle_tennis",
            "idle_squat",
            "idle_yawning",
            "idle_aside",
            "idle_like520",
            "music",
        ]
        return random.choice(idles)

    def get_action_frame_count(self, action_name: str) -> int:
        seq = self.load_sequence(action_name)
        return len(seq)
