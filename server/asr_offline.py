"""Offline ASR sanity check: transcribe saved activation WAVs with the same Vosk model the server uses.
Usage: python server/asr_offline.py <model_dir> <wav> [<wav> ...]"""
import json
import sys
import time
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)
model = Model(sys.argv[1])
for path in sys.argv[2:]:
    with wave.open(path) as w:
        pcm = w.readframes(w.getnframes())
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)
    t0 = time.perf_counter()
    for i in range(0, len(pcm), 2560):
        rec.AcceptWaveform(pcm[i:i + 2560])
    res = json.loads(rec.FinalResult())
    dt = time.perf_counter() - t0
    print(f"{path.split(chr(92))[-1]}: \"{res.get('text', '')}\"  ({len(pcm) / 32000:.2f} s audio, ASR {dt * 1000:.0f} ms)")
