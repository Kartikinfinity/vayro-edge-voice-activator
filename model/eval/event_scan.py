"""Unlabelled-session diagnostic: find speech events (speech-band energy) and report, per event and per model,
the peak single posterior and the peak N-mean posterior (N=3), plus what each model/threshold would trigger."""
import pathlib
import sys

import numpy as np
from scipy import signal

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.eval.eval_stream import detect, load_run_audio, posteriors  # noqa: E402
from model.frontend.psfe import Frontend  # noqa: E402

run = pathlib.Path(sys.argv[1])
models = sys.argv[2:]
audio = load_run_audio(run)
y = signal.sosfilt(signal.butter(4, [300, 4000], btype="band", fs=16000, output="sos"), audio.astype(np.float64))
fr = 320
n = len(y) // fr
e = signal.medfilt(20 * np.log10(np.sqrt(np.mean(y[: n * fr].reshape(n, fr) ** 2, axis=1)) + 1e-9), 5)
act = e > np.percentile(e, 20) + 12
events, i = [], 0
while i < n:
    if act[i]:
        j = i
        while j < n and np.any(act[j:j + 15]):  # bridge 300 ms gaps
            j += 1
        events.append((i * fr / 16000, j * fr / 16000))
        i = j
    i += 1
fe = Frontend()
feats = fe.to_int8(fe.features(audio))
res = {}
for m in models:
    t, p, _, _ = posteriors(pathlib.Path(m), feats)
    sm = np.convolve(p, np.ones(3) / 3, "full")[: len(p)]
    res[m] = (t, p, sm)
print(f"{len(events)} speech events")
for a, b in events:
    cells = []
    for m in models:
        t, p, sm = res[m]
        w = (t >= a) & (t <= b + 1.0)
        cells.append(f"{pathlib.Path(m).parent.name}: p {p[w].max():.2f} mean3 {sm[w].max():.2f}")
    print(f"  {a:6.1f}-{b:6.1f}s ({b - a:.2f}s)  " + " | ".join(cells))
for m in models:
    t, p, sm = res[m]
    for thr in (0.5, 0.6, 0.7, 0.8, 0.9):
        print(f"{pathlib.Path(m).parent.name} thr {thr}: triggers at {[round(x, 1) for x in detect(t, p, thr, 3)]}")
