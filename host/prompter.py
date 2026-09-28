"""Prompt-only session driver (no serial port): prints scripted prompts with the same 'next:' / '<-- NOW' style as
capture.py and logs each prompt's wall-clock start, so server activations (wall_time) and a USB capture running in
parallel can be aligned with the intended utterance.
Usage (host venv): python host/prompter.py <script_file> <label> [--settle-s 3]
Script format as capture.py: `name | seconds | prompt` per line, '#' comments."""
import argparse
import datetime as dt
import json
import pathlib
import time

ap = argparse.ArgumentParser()
ap.add_argument("script")
ap.add_argument("label")
ap.add_argument("--settle-s", type=float, default=3.0)
args = ap.parse_args()
segs = []
for line in pathlib.Path(args.script).read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    name, secs, prompt = [p.strip() for p in line.split("|", 2)]
    segs.append((name, float(secs), prompt))
out = pathlib.Path(__file__).resolve().parents[1] / "evidence" / "prompts"
out.mkdir(parents=True, exist_ok=True)
path = out / f"{dt.datetime.now():%Y%m%d_%H%M%S}_{args.label}.json"
log = {"label": args.label, "script": str(args.script), "segments": []}
print(f"Starting in {args.settle_s:.0f} s ...  first: {segs[0][2]}", flush=True)
time.sleep(args.settle_s)
for k, (name, secs, prompt) in enumerate(segs):
    t0 = time.time()
    log["segments"].append({"name": name, "prompt": prompt, "t0_wall": dt.datetime.fromtimestamp(t0).isoformat(
        timespec="milliseconds"), "t0_epoch": round(t0, 3), "seconds": secs})
    nxt = f"   (next: {segs[k + 1][2]})" if k + 1 < len(segs) else ""
    print(f"\n[{k + 1}/{len(segs)}] {prompt}   <-- NOW{nxt}", flush=True)
    path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    time.sleep(max(0.0, t0 + secs - time.time()))
print(f"\nDone. Prompt log: {path}", flush=True)
