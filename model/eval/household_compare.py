"""v2b vs v3 on the active-household recording of 28 Sep (selection_rule_v3.json, ship rule (a)), plus the M6 v2 command
prompts recorded inside it (reported, not part of the rule).

Each capture session (a device boot) is replayed from its own start with the device-identical pipeline of eval_stream.py
(twin features reset at boot, inference every 6 frames, mean of N=3, threshold, 2 s refractory). Detections inside
`--exclude` windows (session-audio seconds: the M6 test, where the keyword was spoken on purpose) are dropped and those
windows are removed from the exposure. Every remaining detection is a false activation (nobody addressed the device).

Usage (WSL venv):
  python model/eval/household_compare.py --run <household_run_dir> --models v2b:0.8,v3:0.6
         --exclude s5:440:552 --prompts <prompter_json> --prompt-anchor s5:489.18:2026-09-28T20:26:43.452
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.eval.eval_stream import FS, detect, posteriors  # noqa: E402
from model.frontend.psfe import Frontend  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True)
ap.add_argument("--models", default="v2b:0.8,v3:0.6")
ap.add_argument("--n", type=int, default=3)
ap.add_argument("--exclude", nargs="*", default=[], help="session:start_s:end_s")
ap.add_argument("--prompts", default="", help="host/prompter.py JSON log of the M6 v2 prompts")
ap.add_argument("--prompt-anchor", default="", help="session:audio_s:wall_iso of one known instant")
args = ap.parse_args()
run = pathlib.Path(args.run)

# sessions: s1 = audio_16bit_c*.wav, sK = audio_16bit_sK_c*.wav (capture.py names a new file set after each reboot)
sessions = {}
for f in sorted(run.glob("audio_16bit*_c*.wav")):
    m = re.match(r"audio_16bit(?:_s(\d+))?_c(\d+)\.wav", f.name)
    sessions.setdefault(f"s{m.group(1) or 1}", []).append(f)
excl = {}
for e in args.exclude:
    s, a, b = e.split(":")
    excl.setdefault(s, []).append((float(a), float(b)))

fe = Frontend()
models = [(m.split(":")[0], float(m.split(":")[1])) for m in args.models.split(",")]
report = {"run": run.name, "n": args.n, "models": {}, "sessions": {}, "exclude": args.exclude}
post = {}  # (model, session) -> (t, p)
for s, files in sessions.items():
    parts = []
    for f in files:
        with wave.open(str(f)) as w:
            parts.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16))
    audio = np.concatenate(parts)
    secs = len(audio) / FS
    if secs < 5:
        continue
    feats = fe.to_int8(fe.features(audio))
    ex = excl.get(s, [])
    report["sessions"][s] = {"files": [f.name for f in files], "seconds": round(secs, 1),
                             "excluded_s": round(sum(b - a for a, b in ex), 1)}
    # the device's own live decisions in this session (trigger flags written next to each posterior)
    pf = run / ("posteriors_device.bin" if s == "s1" else f"posteriors_device_{s}.bin")
    if pf.exists():
        dev = np.fromfile(pf, dtype=np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")]))
        dt_ = [round(float(fr) / 100, 1) for fr in dev["frame"][dev["trig"] > 0]]
        report["sessions"][s]["device_live_triggers_outside_exclusions"] = [x for x in dt_ if not any(a <= x <= b for a, b in ex)]
    for name, thr in models:
        t, p, _, _ = posteriors(ROOT / "model" / "artifacts" / name / "model_int8.tflite", feats)
        post[(name, s)] = (t, p)
        d = [x for x in detect(t, p, thr, args.n) if not any(a <= x <= b for a, b in ex)]
        mr = report["models"].setdefault(name, {"threshold": thr, "fa": 0, "hours": 0.0, "fa_times": {}})
        mr["fa"] += len(d)
        mr["hours"] += (secs - sum(b - a for a, b in ex)) / 3600
        mr["fa_times"][s] = [round(x, 1) for x in d]
for name, mr in report["models"].items():
    mr["hours"] = round(mr["hours"], 3)
    mr["fa_per_hour"] = round(mr["fa"] / mr["hours"], 2) if mr["hours"] else None

if args.prompts and args.prompt_anchor:
    s, a_s, a_wall = args.prompt_anchor.split(":", 2)
    anchor_audio, anchor_wall = float(a_s), dt.datetime.fromisoformat(a_wall)
    segs = json.loads(pathlib.Path(args.prompts).read_text(encoding="utf-8"))["segments"]
    rows = []
    for g in segs:
        if not g["name"].startswith("v2_"):
            continue
        t0 = anchor_audio + (dt.datetime.fromisoformat(g["t0_wall"]) - anchor_wall).total_seconds()
        # window = the prompt's own 9 s (+0.3 s, as prompt_score); prompt 01 opens 3 s early: the user confirmed starting
        # it during the preceding "Stay quiet" prompt
        lo = t0 - 3.0 if g["name"] == "v2_01" else t0 + 0.3
        hi = t0 + g["seconds"] + 0.3
        row = {"prompt": g["name"], "text": g["prompt"], "audio_s": round(t0, 2)}
        for name, thr in models:
            t, p = post[(name, s)]
            sm = np.convolve(p, np.ones(args.n) / args.n, mode="full")[:len(p)]
            w = (t >= lo) & (t < hi)
            dets = [x for x in detect(t, p, thr, args.n) if lo <= x < hi]
            row[name] = {"hit": bool(dets), "max_p": round(float(p[w].max()), 3), "max_mean3": round(float(sm[w].max()), 3)}
        rows.append(row)
    report["m6_v2_prompts"] = rows
    report["m6_v2_hits"] = {name: sum(r[name]["hit"] for r in rows) for name, _ in models}

out = ROOT / "model" / "artifacts" / "household_compare_20260928.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({k: report[k] for k in ("sessions", "models")}, indent=1))
if "m6_v2_prompts" in report:
    for r in report["m6_v2_prompts"]:
        print(f"{r['prompt']} {r['text'][:40]:40s} " + "  ".join(
            f"{name}: {'HIT ' if r[name]['hit'] else 'miss'} maxp {r[name]['max_p']:.3f} mean3 {r[name]['max_mean3']:.3f}"
            for name, _ in models))
    print("M6 v2 prompt hits:", report["m6_v2_hits"])
print("written", out)
