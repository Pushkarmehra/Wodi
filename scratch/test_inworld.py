import requests
import base64
import tempfile
import os
import time
import ctypes

api_key = 'WWZIN0t1enVEcFIwX01aQ3RVMy1jejNSaXRQUnZTNFA6Z1RYM0FwTk1IQmdfelUxRFJmQXVZNA=='
headers = {'Authorization': f'Basic {api_key}', 'Content-Type': 'application/json'}
payload = {
    'text': 'Hello! Inworld AI Avery voice synthesis is fully operational.',
    'voiceId': 'Avery',
    'modelId': 'inworld-tts-2',
    'timestampType': 'WORD',
    'audioConfig': {'speakingRate': 1},
    'deliveryMode': 'CREATIVE',
    'language': 'AUTO'
}
resp = requests.post('https://api.inworld.ai/tts/v1/voice', json=payload, headers=headers, timeout=10)
data = resp.json()
audio_bytes = base64.b64decode(data['audioContent'])

with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
    f.write(audio_bytes)
    temp_path = f.name

print('Temporary MP3 written to:', temp_path)
mci = ctypes.windll.winmm.mciSendStringW
alias = f'inworld_test_{int(time.time() * 1000)}'
mci(f'open "{temp_path}" type mpegvideo alias {alias}', None, 0, 0)
mci(f'play {alias}', None, 0, 0)
buf = ctypes.create_unicode_buffer(128)
while True:
    mci(f'status {alias} mode', buf, 128, 0)
    mode = buf.value.strip().lower()
    if mode in ('stopped', ''):
        break
    time.sleep(0.04)
mci(f'stop {alias}', None, 0, 0)
mci(f'close {alias}', None, 0, 0)
try:
    os.remove(temp_path)
except Exception:
    pass
print('Playback completed successfully!')
