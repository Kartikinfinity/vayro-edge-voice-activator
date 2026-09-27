"""Score the triggers the DEVICE fired live (posteriors_device.bin trigger flags) against the scripted
ground truth, with the same matching rules as eval_stream.py, and check they equal an offline replay of
the same model/decision parameters on the recorded audio.

Usage (WSL venv): python model/eval/eval_device_triggers.py <run_dir> <model.tflite> --thr 0.9 --n 3
"""
import argparse
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.eval.eval_stream import FE_WIN, FS, HOP, detect, keyword_ends, load_run_audio, posteriors  # noqa: E402
from model.frontend.psfe import Frontend  # noqa: E402


def score(dets, kws, segs, hours):
    used, hits, lags = set(), {}, []
    for k in kws:
        m = [d for d in dets if k["t_start"] <= d <= k["t_end"] + 1.2 and d not in used]
        if m:
            used.add(m[0])
            hits[k["name"]] = True
            lags.append(m[0] - k["t_end"])
    in_kw = [d for d in dets if d not in used and any(k["t_start"] - 0.3 <= d <= k["t_end"] + 2.5 for k in kws)]
    fa = [d for d in dets if d not in used and d not in in_kw]
    where = [next((g["name"] for g in segs if g["t0_s"] <= d < g["t1_s"] + 0.3), "outside_prompts") for d in fa]
    cond = {}
    for k in kws:
        c = "_".join(k["name"].split("_")[1:3])
        cond.setdefault(c, [0, 0])
        cond[c][0] += int(k["name"] in hits)
        cond[c][1] += 1
    return {"detections": len(dets), "keywords": len(kws), "hits": len(hits),
            "recall": round(len(hits) / len(kws), 4) if kws else None,
            "recall_by_condition": {c: f"{a}/{b}" for c, (a, b) in cond.items()},
            "false_activations": len(fa), "fa_locations": where, "extra_in_keyword_prompts": len(in_kw),
            "exposure_hours": round(hours, 4),
            "lag_s": {"median": round(float(np.median(lags)), 3), "min": round(float(np.min(lags)), 3),
                      "max": round(float(np.max(lags)), 3)} if lags else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("model")
    ap.add_argument("--thr", type=float, default=0.9)
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    run = pathlib.Path(a.run)
    audio = load_run_audio(run)
    kws, skipped, _, segs = keyword_ends(run, audio)
    dev = np.fromfile(run / "posteriors_device.bin", dtype=np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")]))
    t_dev = ((FE_WIN + HOP * dev["frame"][dev["trig"] == 1].astype(np.int64)) / FS).tolist()
    fe = Frontend()
    t, p, _, _ = posteriors(pathlib.Path(a.model), fe.to_int8(fe.features(audio)))
    t_off = detect(t, p, a.thr, a.n)
    hours = len(audio) / FS / 3600
    rep = {"run": run.name, "model": a.model, "thr": a.thr, "n": a.n, "keyword_prompts_skipped_by_labeller": skipped,
           "device_live": score(t_dev, kws, segs, hours), "offline_replay": score(t_off, kws, segs, hours),
           "device_trigger_times_equal_offline": [round(x, 3) for x in t_dev] == [round(x, 3) for x in t_off]}
    (run / "device_trigger_eval.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
