#!/usr/bin/env bash
# New-speaker evaluation (no tuning): shipped v4 @ 0.70 and v2b @ 0.80, N=3, on one capture.py keyword session.
# Usage (WSL): bash /mnt/d/ps26172/model/eval/run_newspk.sh <run_dir_name> <tag>
set -euo pipefail
cd /mnt/d/ps26172
export TF_CPP_MIN_LOG_LEVEL=3
for m in v4:0.7 v2b:0.8; do
  v=${m%%:*}; t=${m##*:}
  echo "== $v @ $t"
  ~/.venvs/ps26172/bin/python model/eval/eval_stream.py --model model/artifacts/$v/model_int8.tflite \
      --runs evidence/runs/$1 --n 3 --thresholds $t --tag $2 2>/dev/null | grep -E '^  N=|^==' || true
done
