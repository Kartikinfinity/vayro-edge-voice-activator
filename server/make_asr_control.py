"""ASR control inputs (run in WSL venv, which has soundfile): a clean LibriSpeech utterance written as 16 kHz int16 WAV,
plus the same utterance scaled to the device's measured speech level (-40 dBFS) with the device room bed added."""
import glob
import pathlib
import wave

import numpy as np
import soundfile as sf

out = pathlib.Path("/mnt/d/ps26172/evidence/m6_asr_control")
out.mkdir(parents=True, exist_ok=True)
f = sorted(glob.glob("/home/kartik/ps26172_data/LibriSpeech/dev-clean/*/*/*.flac"))[3]
x, sr = sf.read(f, dtype="float64")
assert sr == 16000
txt = [l for l in open(glob.glob(str(pathlib.Path(f).parent / "*.trans.txt"))[0]) if l.startswith(pathlib.Path(f).stem)][0]
(out / "reference.txt").write_text(txt, encoding="utf-8")


def write(name, y):
    with wave.open(str(out / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.clip(np.round(y), -32768, 32767).astype(np.int16).tobytes())


write("clean.wav", x * 32768 * 0.5)
with wave.open("/mnt/d/ps26172/evidence/runs/20260927_203133_ambient_night_20260927/audio_16bit_c000.wav") as w:
    w.setpos(16000 * 600)
    bed = np.frombuffer(w.readframes(len(x)), dtype=np.int16).astype(np.float64)
rms = np.sqrt(np.mean(x ** 2))
write("device_level_with_bed.wav", x / rms * (32768 * 10 ** (-40 / 20) / np.sqrt(2)) + bed)
print("wrote", out, "reference:", txt.strip())
