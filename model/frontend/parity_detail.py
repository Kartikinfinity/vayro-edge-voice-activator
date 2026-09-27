"""Diagnose parity mismatches: which frames/bands, device vs host values, and whether the difference persists."""
import pathlib
import sys
import wave

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from model.frontend.psfe import Frontend  # noqa: E402

run = pathlib.Path(sys.argv[1])
fe = Frontend()
with wave.open(str(run / "audio_16bit.wav")) as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
rec = np.dtype([("frame", "<u4"), ("end", "<u4"), ("bands", "<u2"), ("v", "<u2", (fe.bands,))])
dev = np.fromfile(run / "features_device.bin", dtype=rec)
host = fe.features(audio)
n = min(len(dev), len(host))
d, h = dev["v"][:n].astype(int), host[:n].astype(int)
for f, b in zip(*np.nonzero(d != h)):
    lo, hi = max(0, f - 2), min(n, f + 3)
    print(f"frame {f} band {b}: device {d[f, b]} host {h[f, b]} | same band frames {lo}..{hi - 1}: "
          f"dev {d[lo:hi, b].tolist()} host {h[lo:hi, b].tolist()}")
