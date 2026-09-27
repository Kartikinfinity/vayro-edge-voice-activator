#!/usr/bin/env bash
# Score S01 session 3 (held-out TEST data, recorded after v2b was frozen).
set -u
cd /mnt/d/ps26172
RUN=evidence/runs/20260927_195253_kw_S01_s3
PY=~/.venvs/ps26172/bin/python
export TF_CPP_MIN_LOG_LEVEL=3
echo "== live device triggers vs offline replay (v2b, thr 0.80, N=3)"
$PY model/eval/eval_device_triggers.py $RUN model/artifacts/v2b/model_int8.tflite --thr 0.8 --n 3 2>/dev/null \
  | grep -E 'device_trigger_times_equal_offline'
for v in v2b v0 v2a; do
  echo "== $v"
  $PY model/eval/eval_stream.py --model model/artifacts/$v/model_int8.tflite --runs $RUN --n 3 \
      --thresholds 0.8,0.9 --tag test_S01_s3 2>/dev/null | grep -E '^  N='
done
