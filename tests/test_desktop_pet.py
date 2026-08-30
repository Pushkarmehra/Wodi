"""
Unit tests for Woody Desktop AI Pet & VPet Simulator Engine.
"""
import os
import sys
import tkinter as tk
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from woody.ui.desktop_pet import WoodyAIPet, GIF_DIR, PET_VOICE_INWORLD
from woody.ui.vpet_engine import VPetEngine, ITEMS_CATALOG, JOBS_CATALOG
from woody.synthesis.tts import TTSEngine


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def test_vpet_simulation_engine():
    print("\n=== 1. Testing VPet Simulation Core Engine ===")
    vpet = VPetEngine(auto_load=False)

    # Initial stats check
    assert vpet.stats.level == 1
    assert vpet.stats.health == 100.0
    assert vpet.stats.fullness == 100.0
    assert vpet.stats.money == 60
    print(f"[OK] Initial stats verified: Level {vpet.stats.level}, Gold {vpet.stats.money}G")


    # EXP and Level-up test
    initial_level = vpet.stats.level
    initial_gold = vpet.stats.money
    leveled = vpet.add_exp(300)
    assert leveled is True
    assert vpet.stats.level > initial_level
    assert vpet.stats.money > initial_gold
    print(f"[OK] Level up verified: Level {vpet.stats.level}, EXP: {vpet.stats.exp}/{vpet.stats.max_exp}")

    # Shop & Item Purchase
    vpet.stats.money = 100
    ok, msg = vpet.buy_item("fish_snack", count=2)
    assert ok is True
    assert vpet.stats.inventory.get("fish_snack", 0) >= 2
    assert vpet.stats.money == 80
    print(f"[OK] Shop purchase verified: {msg}")

    # Item Consumption & Stat Replenishment
    vpet.stats.fullness = 50.0
    vpet.stats.mood = 50.0
    ok, msg = vpet.use_item("fish_snack")
    assert ok is True
    assert vpet.stats.fullness == 75.0
    assert vpet.stats.mood == 60.0
    print(f"[OK] Item consumption verified: Fullness = {vpet.stats.fullness}%, Mood = {vpet.stats.mood}%")

    # Work & Job Progression
    vpet.stats.energy = 100.0
    ok, msg = vpet.start_job("coding")
    assert ok is True
    assert vpet.active_job is not None
    assert vpet.stats.energy < 100.0
    print(f"[OK] Job started: {msg}")

    # Tick job completion
    notifs = vpet.tick(dt_seconds=30.0)
    assert vpet.active_job is None
    assert any("Finished" in n or "完成" in n for n in notifs)
    print(f"[OK] Job completed successfully: {notifs}")


    # Pet Head touch reaction
    mood, msg = vpet.pet_head()
    assert mood >= 60
    assert "Purr" in msg
    print(f"[OK] Pet head interaction: {msg}")

    # Persistence save & reload
    test_save_path = "test_vpet_save.json"
    vpet.save_file = Path(test_save_path)
    save_ok = vpet.save()
    assert save_ok is True
    vpet2 = VPetEngine(save_file=test_save_path)
    assert vpet2.stats.level == vpet.stats.level
    if os.path.exists(test_save_path):
        os.remove(test_save_path)
    print(f"[OK] Persistence save & load verified successfully!")



def test_pet_init_and_assets():
    print("\n=== 2. Verifying Pet GIF Assets ===")
    assert GIF_DIR.exists(), f"GIF directory {GIF_DIR} does not exist"
    
    files = os.listdir(GIF_DIR)
    print(f"Found GIF assets: {files}")
    assert any("idle" in f for f in files)
    assert any("sleep" in f for f in files)
    assert any("walk" in f for f in files)
    print("[OK] All required GIF files present!")

    print("\n=== 3. Testing WoodyAIPet Instantiation & Frames ===")
    root = tk.Tk()
    root.withdraw()  # keep hidden during test
    pet = WoodyAIPet(root=root)

    print(f"Loaded frames:")
    print(f"  - Idle: {len(pet.frames_idle)} frames")
    print(f"  - Idle to Sleep: {len(pet.frames_idle_to_sleep)} frames")
    print(f"  - Sleep: {len(pet.frames_sleep)} frames")
    print(f"  - Sleep to Idle: {len(pet.frames_sleep_to_idle)} frames")
    print(f"  - Walk Left: {len(pet.frames_walk_left)} frames")
    print(f"  - Walk Right: {len(pet.frames_walk_right)} frames")

    assert len(pet.frames_idle) > 0, "Idle frames failed to load"
    assert len(pet.frames_sleep) > 0, "Sleep frames failed to load"
    assert len(pet.frames_walk_left) > 0, "Walk left frames failed to load"
    assert len(pet.frames_walk_right) > 0, "Walk right frames failed to load"

    print("\n=== 4. Testing Pet AI Speech & Thought Bubbles ===")
    pet.say("Hello from Unit Test!", timeout_s=0)
    assert "Hello from Unit Test!" in pet.messagebar_text.cget("text")
    print(f"[OK] Bubble text verified: {pet.messagebar_text.cget('text')}")


    print("\n=== 5. Testing VPet Feeding & Petting Actions ===")
    pet.vpet.stats.inventory["fish_snack"] = 3
    initial_snacks = pet.vpet.stats.inventory.get("fish_snack", 0)
    pet.feed_pet()
    assert pet.vpet.stats.inventory.get("fish_snack", 0) == initial_snacks - 1
    print(f"[OK] Food fed: Remaining = {pet.vpet.stats.inventory.get('fish_snack', 0)}")

    pet.pet_cat()
    assert pet.vpet.stats.mood >= 50
    print(f"[OK] Pet cat petted: Mood = {pet.vpet.stats.mood}%")

    print("\n=== 6. Testing Separate Voice Mode Switching ===")
    tts = TTSEngine(
        engine="inworld",
        voice="Avery",
        pet_voice="community-blcuaurhzmvi",
    )
    assert tts.voice == "Avery", "Default normal voice should be Avery"
    print(f"[OK] Normal mode voice: {tts.voice}")

    # Switch to Pet mode
    tts.set_mode("pet")
    assert tts.voice == "community-blcuaurhzmvi", f"Pet mode voice should be community-blcuaurhzmvi, got {tts.voice}"
    print(f"[OK] Pet mode voice: {tts.voice}")

    # Switch back to Normal mode
    tts.set_mode("normal")
    assert tts.voice == "Avery", f"Normal mode voice should be Avery, got {tts.voice}"
    print(f"[OK] Restored Normal mode voice: {tts.voice}")

    pet.close()
    print("\n==============================================")
    print("ALL VPET SIMULATOR & VOICE TESTS PASSED!")
    print("==============================================")


if __name__ == "__main__":
    test_vpet_simulation_engine()
    test_pet_init_and_assets()
