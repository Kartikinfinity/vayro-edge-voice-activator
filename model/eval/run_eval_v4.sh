#!/usr/bin/env bash
# v4 evaluation exactly as model/artifacts/selection_rule_v4.json states: threshold from S01 s2 (validation), then the
# held-out checks (a)-(c). Rule (d) needs the fresh command session (model/eval/prompt_hits.py) and is applied later.
# Usage (WSL): bash /mnt/d/ps26172/model/eval/run_eval_v4.sh
set -euo pipefail
cd /mnt/d/ps26172
export TF_CPP_MIN_LOG_LEVEL=3
PY=~/.venvs/ps26172/bin/python
A=model/artifacts/v4
R=evidence/runs
echo "== threshold rule on S01 s2 (validation)"
$PY model/eval/eval_stream.py --model $A/model_int8.tflite --runs $R/20260927_151127_kw_S01_s2 --n 3 --tag val_s2 > /dev/null 2>&1
T=$($PY - <<'EOF'
import json
r = json.load(open("model/artifacts/v4/eval_val_s2.json"))
sw = next(iter(r["runs"].values()))["sweep"]
rows = sorted(((s["threshold"], s["prompt_score"]["kw_prompts_hit"], s["prompt_score"]["kw_prompts"]) for s in sw if s["n"] == 3))
ok = [t for t, h, n in rows if h >= 20]
if ok:
    thr = max(ok)
else:  # maximum recall, ties -> higher threshold
    best = max(h for _, h, _ in rows)
    thr = max(t for t, h, _ in rows if h == best)
print(f"{thr}")
import sys
print("  s2 prompt score N=3: " + ", ".join(f"{t}: {h}/{n}" for t, h, n in rows), file=sys.stderr)
EOF
)
echo "  selected threshold: $T"
echo "== (b) S01 s3 TEST @ $T"
$PY model/eval/eval_stream.py --model $A/model_int8.tflite --runs $R/20260927_195253_kw_S01_s3 --n 3 --thresholds $T --tag test_S01_s3 2>/dev/null | grep -E '^  N=' || true
echo "== (c) held-out night c005-c009 @ $T"
N=$R/20260927_203133_ambient_night_20260927
$PY model/eval/eval_stream.py --model $A/model_int8.tflite --runs $N/audio_16bit_c005.wav $N/audio_16bit_c006.wav $N/audio_16bit_c007.wav $N/audio_16bit_c008.wav $N/audio_16bit_c009.wav --n 3 --thresholds $T --tag heldout_night 2>/dev/null | grep -E '^  N=|^==' || true
echo "== (a) household (held-out = s5 >= 3600 s) + M6 v2 prompts, v2b@0.8 vs v4@$T"
$PY model/eval/household_compare.py --run $R/20260928_193953_household_eve_20260928 --models v2b:0.8,v4:$T \
    --exclude s5:440:552 --prompts evidence/prompts/20260928_202559_m6_v2_S01.json \
    --prompt-anchor s5:489.18:2026-09-28T20:26:43.452 --out household_compare_v4.json 2>/dev/null | grep -E '^v2_|M6 v2|written' || true
$PY - <<'EOF'
import json
r = json.load(open("model/artifacts/household_compare_v4.json"))
for m, d in r["models"].items():
    held = [x for x in d["fa_times"].get("s5", []) if x >= 3600]
    print(f"  {m}@{d['threshold']}: held-out s5>=3600 s: {len(held)} FA in 0.8625 h; whole recording (v4: includes training hours): {d['fa']} FA / {d['hours']} h")
EOF
echo "done $(date -Is)"
