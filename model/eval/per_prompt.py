"""Per-prompt diagnostic: labeller span, peak posterior inside the prompt, and device triggers nearby."""
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.eval.eval_stream import FE_WIN, FS, HOP, keyword_ends, load_run_audio  # noqa: E402

run = pathlib.Path(sys.argv[1])
audio = load_run_audio(run)
kws, skipped, _, segs = keyword_ends(run, audio)
span = {k["name"]: k for k in kws}
dev = np.fromfile(run / "posteriors_device.bin", dtype=np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")]))
t = (FE_WIN + HOP * dev["frame"].astype(np.int64)) / FS
p = (dev["raw"].astype(np.float32) + 128) / 256.0  # output quant (1/256, -128)
for g in segs:
    if not g["name"].startswith(("kw_", "neg_", "move", "talk")):
        continue
    m = (t >= g["t0_s"]) & (t < g["t1_s"] + 1.0)
    trig = [round(x - g["t0_s"], 2) for x in t[m & (dev["trig"] == 1)]]
    k = span.get(g["name"])
    s = f"span {k['t_start'] - g['t0_s']:.2f}-{k['t_end'] - g['t0_s']:.2f}s pk{k['peak_db_above_local_floor']}dB" if k else "span -"
    print(f"{g['name']:18} {s:30} max_p {p[m].max():.3f}  triggers@ {trig}")
