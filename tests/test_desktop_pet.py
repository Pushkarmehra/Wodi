"""
Unit tests for Woody Desktop AI Pet companion and separate voice mode switching.
"""
import os
import sys
import tkinter as tk

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from woody.ui.desktop_pet import WoodyAIPet, GIF_DIR, PET_VOICE_INWORLD
from woody.synthesis.tts import TTSEngine


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def test_pet_init_and_assets():
    print("=== 1. Verifying Pet GIF Assets ===")
    assert GIF_DIR.exists(), f"GIF directory {GIF_DIR} does not exist"
    
    files = os.listdir(GIF_DIR)
    print(f"Found GIF assets: {files}")
    assert any("idle" in f for f in files)
    assert any("sleep" in f for f in files)
    assert any("walk" in f for f in files)
    print("[OK] All required GIF files present!")

    print("\n=== 2. Testing WoodyAIPet Instantiation & Frames ===")
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

    print("\n=== 3. Testing Pet AI Speech & Thought Bubbles ===")
    pet.say("Hello from Unit Test!", timeout_s=0)
    assert "Hello from Unit Test!" in pet.bubble_label.cget("text")
    print(f"[OK] Bubble text verified: {pet.bubble_label.cget('text')}")

    print("\n=== 4. Testing Pet Feeding & Petting Actions ===")
    initial_snacks = pet.fish_snacks
    pet.feed_pet()
    assert pet.fish_snacks == initial_snacks - 1
    print(f"[OK] Fish snack fed: Remaining = {pet.fish_snacks}")

    pet.pet_cat()
    assert pet.happiness == 100
    print(f"[OK] Pet cat petted: Happiness = {pet.happiness}%")

    print("\n=== 5. Testing Separate Voice Mode Switching ===")
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
    print("ALL DESKTOP PET & VOICE TESTS PASSED!")
    print("==============================================")


if __name__ == "__main__":
    test_pet_init_and_assets()
