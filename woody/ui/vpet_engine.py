"""
VPet Simulator Engine for Woody AI Operating System.

Directly integrates and parses the official data from the LorisYounger/VPet repository
at `vpet/VPet-main/VPet-Simulator.Windows/mod/0000_core/`:
  - 100+ Authentic Foods, Drinks, Drugs, Gifts from `food.lps`, `drug.lps`, `gift.lps`, `moredrink.lps`
  - Fully translated to English using official VPet translation dictionaries in `lang/en/*.lps`
  - Real-time Work & Study jobs (Python AI Coding, Streaming, Calligraphy, System Analytics, Math, Literature)
  - Full RPG stats: Level & EXP, Money $, Health, Fullness (Hunger), Thirst, Energy, Mood, Likability
  - Persistence: Save/load state to ~/.woody/vpet_save.json
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from woody.utils.logging import get_logger

log = get_logger(__name__)

# Paths
_MODULE_DIR = Path(__file__).parent
_ROOT_DIR = _MODULE_DIR.parent.parent
VPET_MAIN_DIR = _ROOT_DIR / "vpet" / "VPet-main"
VPET_MOD_CORE = VPET_MAIN_DIR / "VPet-Simulator.Windows" / "mod" / "0000_core"

SAVE_DIR = Path.home() / ".woody"
SAVE_FILE = SAVE_DIR / "vpet_save.json"


@dataclass
class Item:
    id: str
    name: str
    category: str       # "food" | "drink" | "medicine" | "gift"
    price: float        # Gold coins / $
    icon: str = "🍲"
    fullness: float = 0.0
    thirst: float = 0.0
    energy: float = 0.0
    health: float = 0.0
    mood: float = 0.0
    likability: float = 0.0
    exp: int = 0
    description: str = ""


def _load_en_dictionary() -> dict[str, str]:
    """Load all English translation mappings from official VPet lang/en/ files."""
    en_dir = VPET_MOD_CORE / "lang" / "en"
    d: dict[str, str] = {}
    if en_dir.exists():
        for lps in en_dir.glob("*.lps"):
            try:
                for line in lps.read_text(encoding="utf-8-sig").splitlines():
                    if line.endswith(":|") and "#" in line:
                        parts = line[:-2].split("#", 1)
                        if len(parts) == 2:
                            k = parts[0].strip()
                            v = parts[1].strip()
                            if k and v:
                                d[k] = v
            except Exception:
                pass
    return d


EN_DICT = _load_en_dictionary()


def _parse_lps_file(lps_path: Path, category_override: str | None = None) -> list[Item]:
    """Parse official VPet LinePutScript (.lps) food and item definitions with English translation."""
    items: list[Item] = []
    if not lps_path.exists():
        return items

    try:
        lines = lps_path.read_text(encoding="utf-8-sig").splitlines()
        for line in lines:
            line = line.strip()
            if not line or not line.startswith("food:|"):
                continue

            props: dict[str, str] = {}
            for tok in line.split(":|"):
                if "#" in tok:
                    k, v = tok.split("#", 1)
                    k = k.replace("food:|", "").strip()
                    props[k] = v.strip()

            raw_name = props.get("name", "")
            if not raw_name:
                continue

            # Translate name to English using official dictionary or fallback
            en_name = EN_DICT.get(raw_name, raw_name)

            item_type = props.get("type", "Food").lower()
            cat = category_override or ("drink" if "drink" in item_type else "medicine" if "drug" in item_type else "gift" if "gift" in item_type else "food")

            # Icon mapping
            icon = "🍲"
            if cat == "drink":
                icon = "🧋" if "tea" in en_name.lower() or "milk" in en_name.lower() else "💧" if "water" in en_name.lower() else "⚡" if "energy" in en_name.lower() or "coffee" in en_name.lower() else "🥤"
            elif cat == "medicine":
                icon = "💊" if "pill" in en_name.lower() or "vitamin" in en_name.lower() else "🩹" if "bandage" in en_name.lower() else "🧪"
            elif cat == "gift":
                icon = "🎁" if "box" in en_name.lower() or "gift" in en_name.lower() else "🧸"
            else:
                icon = "🍔" if "burger" in en_name.lower() else "🍜" if "noodle" in en_name.lower() or "ramen" in en_name.lower() else "🍰" if "cake" in en_name.lower() else "🐟" if "fish" in en_name.lower() else "🍖"

            try:
                price = float(props.get("price", "10.0"))
            except ValueError:
                price = 10.0

            try:
                exp_v = int(float(props.get("Exp", "5")))
            except ValueError:
                exp_v = 5

            try:
                food_v = float(props.get("StrengthFood", "0"))
            except ValueError:
                food_v = 0.0

            try:
                drink_v = float(props.get("StrengthDrink", "0"))
            except ValueError:
                drink_v = 0.0

            try:
                energy_v = float(props.get("Strength", "0"))
            except ValueError:
                energy_v = 0.0

            try:
                health_v = float(props.get("Health", "0"))
            except ValueError:
                health_v = 0.0

            try:
                mood_v = float(props.get("Feeling", "0"))
            except ValueError:
                mood_v = 0.0

            raw_desc = props.get("desc", f"Official VPet {en_name} item.")
            en_desc = EN_DICT.get(raw_desc, raw_desc)
            item_id = raw_name.lower().replace(" ", "_")

            items.append(
                Item(
                    id=item_id,
                    name=en_name,
                    category=cat,
                    price=price,
                    icon=icon,
                    fullness=food_v,
                    thirst=drink_v,
                    energy=energy_v,
                    health=health_v,
                    mood=mood_v,
                    exp=exp_v,
                    description=en_desc,
                )
            )
    except Exception as e:
        log.warning("vpet.lps_parse_error", file=str(lps_path), error=str(e))

    return items


def load_all_vpet_items() -> dict[str, Item]:
    """Load items from all official VPet .lps data files plus core defaults."""
    catalog: dict[str, Item] = {}

    # Core base items for English & test compatibility
    base_defaults = [
        Item("fish_snack", "Grilled Fish", "food", 10.0, "🐟", fullness=25, mood=10, exp=15, description="Fresh grilled fish treat! Restores hunger."),
        Item("burger", "Burger Deluxe", "food", 18.0, "🍔", fullness=45, mood=15, exp=20, description="Hearty deluxe burger meal."),
        Item("cake", "Strawberry Cake", "food", 15.0, "🍰", fullness=20, mood=30, exp=10, description="Sweet fluffy strawberry cake."),
        Item("water", "Spring Water", "drink", 4.0, "💧", thirst=35, health=5, exp=5, description="Pure refreshing spring water."),
        Item("boba_tea", "Boba Milk Tea", "drink", 12.0, "🧋", thirst=35, mood=20, exp=10, description="Sweet milk tea with tapioca pearls."),
        Item("bandage", "Health Bandage", "medicine", 15.0, "🩹", health=30, mood=-5, exp=5, description="First aid bandage."),
        Item("vitamin", "Super Vitamin", "medicine", 25.0, "💊", health=55, energy=20, exp=15, description="Nourishing multivitamins."),
        Item("potion", "Elixir Potion", "medicine", 50.0, "🧪", health=100, mood=20, fullness=20, thirst=20, exp=40, description="Magical elixir that cures all."),
        Item("music_box", "Music Box", "gift", 30.0, "🎁", mood=45, likability=20, exp=50, description="Plays a soothing melody."),
        Item("plushie", "Plushie Doll", "gift", 25.0, "🧸", mood=35, likability=15, exp=30, description="Cute cuddly companion plushie."),
    ]
    for it in base_defaults:
        catalog[it.id] = it

    # Load 120+ official VPet items from VPet-main LPS files
    food_dir = VPET_MOD_CORE / "food"
    if food_dir.exists():
        for lps_file, cat in [
            (food_dir / "food.lps", None),
            (food_dir / "moredrink.lps", "drink"),
            (food_dir / "drug.lps", "medicine"),
            (food_dir / "gift.lps", "gift"),
            (food_dir / "timelimit.lps", None),
        ]:
            if lps_file.exists():
                parsed = _parse_lps_file(lps_file, category_override=cat)
                for item in parsed:
                    catalog[item.id] = item

    return catalog


ITEMS_CATALOG: dict[str, Item] = load_all_vpet_items()


@dataclass
class JobTask:
    id: str
    name: str
    category: str       # "work" | "study"
    duration_s: int
    gold_reward: int
    exp_reward: int
    energy_cost: float
    food_cost: float = 0.0
    thirst_cost: float = 0.0
    mood_reward: float = 0.0
    description: str = ""


# Official & Custom VPet Work & Study Tasks (All in English)
JOBS_CATALOG: dict[str, JobTask] = {
    # ── Work (Earn Gold + EXP) ──
    "coding": JobTask(
        id="coding", name="Python AI Coding", category="work", duration_s=25,
        gold_reward=35, exp_reward=45, energy_cost=15, food_cost=8,
        description="Developing Python AI agents and Windows OS automation."
    ),
    "calligraphy": JobTask(
        id="calligraphy", name="Art & Calligraphy", category="work", duration_s=20,
        gold_reward=25, exp_reward=35, energy_cost=10, food_cost=5,
        description="Writing beautiful calligraphy scrolls and art designs."
    ),
    "streaming": JobTask(
        id="streaming", name="Gaming & Live Streaming", category="work", duration_s=25,
        gold_reward=45, exp_reward=50, energy_cost=20, thirst_cost=10,
        description="Streaming gameplay and entertaining fans online."
    ),
    "sausage": JobTask(
        id="sausage", name="Grilled Snack Stand", category="work", duration_s=15,
        gold_reward=20, exp_reward=25, energy_cost=12, food_cost=4,
        description="Cooking delicious snacks at the street food stall."
    ),
    "office": JobTask(
        id="office", name="System Data Analytics", category="work", duration_s=18,
        gold_reward=28, exp_reward=30, energy_cost=12, food_cost=6,
        description="Analyzing system performance logs and writing reports."
    ),

    # ── Study (High EXP + Intelligence) ──
    "ai_ml": JobTask(
        id="ai_ml", name="AI & Neural Networks", category="study", duration_s=25,
        gold_reward=0, exp_reward=80, energy_cost=15, food_cost=8,
        description="Studying machine learning algorithms, LLMs, and transformers."
    ),
    "math": JobTask(
        id="math", name="Discrete Math & Logic", category="study", duration_s=20,
        gold_reward=0, exp_reward=60, energy_cost=12, food_cost=5,
        description="Mastering mathematical proofs and algorithm optimizations."
    ),
    "literature": JobTask(
        id="literature", name="World Literature & Poetry", category="study", duration_s=15,
        gold_reward=0, exp_reward=45, energy_cost=8, mood_reward=15,
        description="Reading classical literature and philosophical essays."
    ),
}


@dataclass
class PetStats:
    name: str = "Woody"
    level: int = 1
    exp: int = 0
    max_exp: int = 100
    money: int = 60
    health: float = 100.0
    fullness: float = 100.0
    thirst: float = 100.0
    energy: float = 100.0
    mood: float = 100.0
    likability: float = 100.0
    inventory: dict[str, int] = field(default_factory=lambda: {
        "fish_snack": 3,
        "water": 2,
        "bandage": 1,
    })
    total_earned_gold: int = 0
    total_jobs_completed: int = 0
    last_saved_time: float = field(default_factory=time.time)


class VPetEngine:
    """
    Complete VPet RPG Life Simulation Core (English Localization).
    """

    def __init__(
        self,
        on_level_up: Callable[[int], None] | None = None,
        save_file: Path | str | None = None,
        auto_load: bool = True,
    ) -> None:
        self.stats = PetStats()
        self.on_level_up = on_level_up
        self.save_file = Path(save_file) if save_file else SAVE_FILE

        self.active_job: JobTask | None = None
        self.job_time_remaining: float = 0.0

        if auto_load:
            self.load()

    def _clamp_stats(self) -> None:
        self.stats.health = max(0.0, min(100.0, self.stats.health))
        self.stats.fullness = max(0.0, min(100.0, self.stats.fullness))
        self.stats.thirst = max(0.0, min(100.0, self.stats.thirst))
        self.stats.energy = max(0.0, min(100.0, self.stats.energy))
        self.stats.mood = max(0.0, min(100.0, self.stats.mood))
        self.stats.likability = max(0.0, min(100.0, self.stats.likability))
        self.stats.money = max(0, self.stats.money)

    def tick(self, dt_seconds: float, is_sleeping: bool = False) -> list[str]:
        notifications: list[str] = []

        if is_sleeping:
            self.stats.energy = min(100.0, self.stats.energy + (1.5 * (dt_seconds / 10.0)))
            self.stats.health = min(100.0, self.stats.health + (0.4 * (dt_seconds / 10.0)))
            self.stats.fullness = max(0.0, self.stats.fullness - (0.1 * (dt_seconds / 10.0)))
            self.stats.thirst = max(0.0, self.stats.thirst - (0.15 * (dt_seconds / 10.0)))
        else:
            self.stats.fullness = max(0.0, self.stats.fullness - (0.25 * (dt_seconds / 10.0)))
            self.stats.thirst = max(0.0, self.stats.thirst - (0.35 * (dt_seconds / 10.0)))
            self.stats.energy = max(0.0, self.stats.energy - (0.15 * (dt_seconds / 10.0)))

            if self.stats.fullness < 30 or self.stats.thirst < 30:
                self.stats.mood = max(0.0, self.stats.mood - (0.4 * (dt_seconds / 10.0)))

            if self.stats.fullness <= 5 or self.stats.thirst <= 5:
                self.stats.health = max(0.0, self.stats.health - (0.8 * (dt_seconds / 10.0)))
                if self.stats.health < 20 and int(time.time()) % 30 == 0:
                    notifications.append("⚠️ Pet health is critically low! Feed or heal immediately!")

        if self.active_job:
            self.job_time_remaining -= dt_seconds
            if self.job_time_remaining <= 0:
                reward_msg = self._complete_active_job()
                notifications.append(reward_msg)

        self._clamp_stats()
        return notifications

    def add_exp(self, amount: int) -> bool:
        self.stats.exp += amount
        leveled_up = False

        while self.stats.exp >= self.stats.max_exp:
            self.stats.exp -= self.stats.max_exp
            self.stats.level += 1
            self.stats.max_exp = int(self.stats.level * 100 * 1.15)
            self.stats.money += 35 + (self.stats.level * 5)
            self.stats.health = 100.0
            self.stats.energy = 100.0
            self.stats.mood = 100.0
            leveled_up = True
            log.info("vpet.level_up", level=self.stats.level, bonus=35 + (self.stats.level * 5))
            if self.on_level_up:
                self.on_level_up(self.stats.level)

        return leveled_up

    # ── Job & Study System ────────────────────────────────────────────────────

    def start_job(self, job_id: str) -> tuple[bool, str]:
        if job_id not in JOBS_CATALOG:
            return False, f"Unknown job: {job_id}"

        job = JOBS_CATALOG[job_id]
        if self.stats.energy < job.energy_cost:
            return False, f"Too tired for {job.name}! Energy: {int(self.stats.energy)}% (Requires {int(job.energy_cost)}%). Nap first!"

        if self.stats.fullness < job.food_cost:
            return False, f"Too hungry for {job.name}! Please feed your pet first!"

        self.active_job = job
        self.job_time_remaining = float(job.duration_s)
        self.stats.energy = max(0.0, self.stats.energy - job.energy_cost)
        self.stats.fullness = max(0.0, self.stats.fullness - job.food_cost)
        self.stats.thirst = max(0.0, self.stats.thirst - job.thirst_cost)
        self._clamp_stats()

        verb = "Working on" if job.category == "work" else "Studying"
        return True, f"{verb}: {job.name} ({job.duration_s}s)"

    def cancel_job(self) -> str:
        if not self.active_job:
            return "No active job to cancel."
        name = self.active_job.name
        self.active_job = None
        self.job_time_remaining = 0
        return f"Cancelled {name}."

    def _complete_active_job(self) -> str:
        if not self.active_job:
            return ""

        job = self.active_job
        self.active_job = None
        self.job_time_remaining = 0

        self.stats.money += job.gold_reward
        self.stats.total_earned_gold += job.gold_reward
        self.stats.total_jobs_completed += 1
        self.stats.mood = min(100.0, self.stats.mood + job.mood_reward)

        leveled = self.add_exp(job.exp_reward)
        self.save()

        gold_str = f"+🪙 ${job.gold_reward}  " if job.gold_reward > 0 else ""
        lvl_str = " ⭐ LEVEL UP!" if leveled else ""
        return f"🎉 Finished {job.name}! {gold_str}+⭐ {job.exp_reward} EXP{lvl_str}"

    # ── Shop & Inventory System ───────────────────────────────────────────────

    def buy_item(self, item_id: str, count: int = 1) -> tuple[bool, str]:
        if item_id not in ITEMS_CATALOG:
            return False, "Item not found in catalog."

        item = ITEMS_CATALOG[item_id]
        total_cost = int(item.price * count)
        if self.stats.money < total_cost:
            return False, f"Not enough Money! Costs ${total_cost}, you have ${self.stats.money}."

        self.stats.money -= total_cost
        curr = self.stats.inventory.get(item_id, 0)
        self.stats.inventory[item_id] = curr + count
        self.save()
        return True, f"Purchased {count}x {item.icon} {item.name}! (-${total_cost})"

    def use_item(self, item_id: str) -> tuple[bool, str]:
        if self.stats.inventory.get(item_id, 0) <= 0:
            return False, f"You don't have any {item_id}!"

        if item_id not in ITEMS_CATALOG:
            return False, "Unknown item."

        item = ITEMS_CATALOG[item_id]
        self.stats.inventory[item_id] -= 1
        if self.stats.inventory[item_id] <= 0:
            del self.stats.inventory[item_id]

        self.stats.fullness = min(100.0, self.stats.fullness + item.fullness)
        self.stats.thirst = min(100.0, self.stats.thirst + item.thirst)
        self.stats.energy = min(100.0, self.stats.energy + item.energy)
        self.stats.health = min(100.0, self.stats.health + item.health)
        self.stats.mood = min(100.0, self.stats.mood + item.mood)
        self.stats.likability = min(100.0, self.stats.likability + item.likability)

        leveled = False
        if item.exp > 0:
            leveled = self.add_exp(item.exp)

        self._clamp_stats()
        self.save()

        lvl_txt = " ⭐ LEVEL UP!" if leveled else ""
        return True, f"Consumed {item.icon} {item.name}! Stats restored.{lvl_txt}"

    def pet_head(self) -> tuple[int, str]:
        self.stats.mood = min(100.0, self.stats.mood + 15.0)
        self.stats.likability = min(100.0, self.stats.likability + 8.0)
        leveled = self.add_exp(12)
        self._clamp_stats()
        self.save()

        lvl_txt = " ⭐ LEVEL UP!" if leveled else ""
        return int(self.stats.mood), f"✨ *Purrrrr*... Feeling loved! +12 EXP{lvl_txt}"

    # ── Persistence (Save / Load) ─────────────────────────────────────────────

    def save(self) -> bool:
        try:
            self.save_file.parent.mkdir(parents=True, exist_ok=True)
            self.stats.last_saved_time = time.time()
            data = asdict(self.stats)
            self.save_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            log.warning("vpet.save_error", error=str(e))
            return False

    def load(self) -> bool:
        if not self.save_file.exists():
            return False
        try:
            raw = self.save_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            for k, v in data.items():
                if hasattr(self.stats, k):
                    if k == "name" and v == "Ayaka":
                        v = "Woody"
                    setattr(self.stats, k, v)
            self._clamp_stats()
            log.info("vpet.loaded_save", level=self.stats.level, money=self.stats.money)
            return True
        except Exception as e:
            log.warning("vpet.load_error", error=str(e))
            return False
