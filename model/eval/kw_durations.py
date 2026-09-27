"""Measure real keyword utterance durations per condition (energy-located, same method as eval_stream),
and the durations of the TTS positives, to check the model window / TTS speed range against reality."""
import csv
import json
import pathlib
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from model.eval.eval_stream import keyword_ends, load_run_audio  # noqa: E402
from model.data.build_dataset import trim, to16k  # noqa: E402

out = {}
for rd in sys.argv[1:]:
    run = pathlib.Path(rd)
    kws, skipped, floor, _ = keyword_ends(run, load_run_audio(run))
    by = {}
    for k in kws:
        by.setdefault("_".join(k["name"].split("_")[1:3]), []).append(round(k["t_end"] - k["t_start"], 2))
    out[run.name] = {"floor_dbfs": floor, "durations_s": by, "skipped": skipped}
    for c, d in by.items():
        print(f"{run.name} {c:12} n={len(d)}  durations {d}")

tts = pathlib.Path.home() / "ps26172_data" / "tts"
rows = [r for r in csv.DictReader(open(tts / "manifest.csv", encoding="utf-8")) if r["label"] == "pos"][::10]
dur = []
for r in rows:
    x, sr = sf.read(tts / r["file"], dtype="float64")
    dur.append(len(trim(to16k(x, sr))) / 16000)
dur = np.array(dur)
print(f"TTS positives (every 10th, n={len(dur)}): duration p5/p50/p95/max = "
      f"{np.percentile(dur, 5):.2f}/{np.median(dur):.2f}/{np.percentile(dur, 95):.2f}/{dur.max():.2f} s")
out["tts_pos_duration_s"] = {"p5": float(np.percentile(dur, 5)), "p50": float(np.median(dur)),
                             "p95": float(np.percentile(dur, 95)), "max": float(dur.max()), "n": int(len(dur))}
print(json.dumps(out)[:0])
