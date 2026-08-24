import numpy as np
import sounddevice as sd
import time

def play_siri_wake_chime():
    sr = 44100
    # Two rising bell tones: D5 (587.33 Hz) for 0.08s, then A5 (880 Hz) for 0.14s
    d1, d2 = 0.08, 0.14
    t1 = np.linspace(0, d1, int(sr * d1), endpoint=False)
    t2 = np.linspace(0, d2, int(sr * d2), endpoint=False)
    
    # Smooth sine with gentle envelope
    env1 = np.sin(np.pi * t1 / d1) ** 1.5
    env2 = np.sin(np.pi * t2 / d2) ** 1.5
    
    tone1 = np.sin(2 * np.pi * 587.33 * t1) * env1 * 0.15
    tone2 = np.sin(2 * np.pi * 880.00 * t2) * env2 * 0.18
    
    chime = np.concatenate([tone1, tone2]).astype(np.float32)
    sd.play(chime, samplerate=sr, blocking=True)

if __name__ == "__main__":
    print("Playing Siri activation chime...")
    play_siri_wake_chime()
    print("Done!")
