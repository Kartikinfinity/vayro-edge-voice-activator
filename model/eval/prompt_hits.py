"""Per-prompt keyword hits for several models on one capture.py script run (e.g. host/scripts/m6_commands_v3.txt),
replayed with the device-identical pipeline of eval_stream.py (reset at boot, stride 6, mean of N=3, 2 s refractory).
A prompt is HIT when a detection falls in [t0 + 0.3 s, t1 + 0.3 s] of its window (the household_compare.py window);
detections outside every prompt window are false activations. The deployed model's live device triggers are listed
as a replay check.

Usage (WSL venv): python model/eval/prompt_hits.py --run <run_dir> --models v2b:0.8,v4:0.6 [--prefix v3_]"""
import argparse
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.eval.eval_stream import detect, load_run_audio, posteriors  # noqa: E402
from model.frontend.psfe import Frontend  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True)
ap.add_argument("--models", required=True)
ap.add_argument("--prefix", default="v3_")
ap.add_argument("--n", type=int, default=3)
args = ap.parse_args()
run = pathlib.Path(args.run)
summ = json.loads((run / "capture_summary.json").read_text(encoding="utf-8"))
segs = summ["script_segments"]
prompts = [g for g in segs if g["name"].startswith(args.prefix)]
fe = Frontend()
feats = fe.to_int8(fe.features(load_run_audio(run)))
rep = {"run": run.name, "n": args.n, "prompts": [g["name"] for g in prompts], "models": {}}
dev = [round(k["t_ms"] / 1000, 2) for k in summ.get("device_kw_triggers", []) if not k.get("synthetic")]
rep["device_live_triggers_s"] = dev
for m in args.models.split(","):
    name, thr = m.split(":")
    t, p, _, _ = posteriors(ROOT / "model" / "artifacts" / name / "model_int8.tflite", feats)
    sm = np.convolve(p, np.ones(args.n) / args.n, mode="full")[:len(p)]
    dets = detect(t, p, float(thr), args.n)
    rows, used = [], set()
    for g in prompts:
        lo, hi = g["t0_s"] + 0.3, g["t1_s"] + 0.3
        hit = [d for d in dets if lo <= d < hi]
        used.update(hit)
        w = (t >= lo) & (t < hi)
        rows.append({"prompt": g["name"], "text": g["prompt"], "hit": bool(hit),
                     "max_p": round(float(p[w].max()), 3), "max_mean3": round(float(sm[w].max()), 3)})
    fa = [round(d, 2) for d in dets if d not in used]
    rep["models"][name] = {"threshold": float(thr), "hits": sum(r["hit"] for r in rows), "of": len(rows),
                           "false_activations_outside_prompts": fa, "detections_s": [round(d, 2) for d in dets],
                           "rows": rows}
out = ROOT / "model" / "artifacts" / f"prompt_hits_{run.name}.json"
out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
for g_i, g in enumerate(prompts):
    print(f"{g['name']} {g['prompt'][:44]:44s} " + "  ".join(
        f"{n}: {'HIT ' if r['rows'][g_i]['hit'] else 'miss'} maxp {r['rows'][g_i]['max_p']:.3f} m3 {r['rows'][g_i]['max_mean3']:.3f}"
        for n, r in rep["models"].items()))
for n, r in rep["models"].items():
    print(f"{n}@{r['threshold']}: {r['hits']}/{r['of']} prompts, FA outside prompts {r['false_activations_outside_prompts']}")
print("device live triggers (s):", dev)
print("written", out)
