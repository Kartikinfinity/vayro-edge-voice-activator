"""Diagnose empty ASR transcripts: same WAVs through Vosk raw vs. high-pass (100 Hz) + gain to a target speech level.
Usage: python server/asr_level_test.py <model_dir> <wav> [...]"""
import json
import sys
import wave

import numpy as np
from scipy import signal
from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)
model = Model(sys.argv[1])
SOS_HP = signal.butter(2, 100, btype="high", fs=16000, output="sos")
SOS_HP8 = signal.butter(8, 150, btype="high", fs=16000, output="sos")  # steep: removes the 60-70 Hz fan rumble
SOS_SP = signal.butter(4, [300, 4000], btype="band", fs=16000, output="sos")


GRAMMAR = open(__file__.replace("asr_level_test.py", "commands.json"), encoding="utf-8").read()


def asr(x, grammar=None):
    rec = KaldiRecognizer(model, 16000, grammar) if grammar else KaldiRecognizer(model, 16000)
    pcm = np.clip(np.round(x), -32768, 32767).astype(np.int16).tobytes()
    for i in range(0, len(pcm), 2560):
        rec.AcceptWaveform(pcm[i:i + 2560])
    return json.loads(rec.FinalResult()).get("text", "")


for path in sys.argv[2:]:
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    hp = signal.sosfilt(SOS_HP, x)
    sp = signal.sosfilt(SOS_SP, x)
    # speech level = 95th percentile of 50 ms speech-band RMS
    fr = 800
    n = len(sp) // fr
    lev = np.sqrt(np.mean(sp[: n * fr].reshape(n, fr) ** 2, axis=1))
    speech_rms = np.percentile(lev, 95)
    g = 10 ** (-20 / 20) * 32768 / np.sqrt(2) / max(speech_rms, 1.0)  # speech to ~-20 dBFS
    print(f"{path.split(chr(92))[-1]}: speech p95 {20 * np.log10(speech_rms * np.sqrt(2) / 32768):.1f} dBFS, gain {20 * np.log10(g):.1f} dB")
    print(f"   raw          : \"{asr(x)}\"")
    print(f"   hp2@100+gain : \"{asr(hp * g)}\"")
    print(f"   hp8@150+gain : \"{asr(signal.sosfilt(SOS_HP8, x) * g)}\"")
    print(f"   hp8+gain+GRAMMAR: \"{asr(signal.sosfilt(SOS_HP8, x) * g, GRAMMAR)}\"")
