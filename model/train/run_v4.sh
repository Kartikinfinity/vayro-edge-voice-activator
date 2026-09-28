#!/usr/bin/env bash
# v4 build (selection_rule_v4.json incl. amendment 1): v3 recipe + keyword+continuation positives + household negatives/beds.
# Usage (WSL): bash /mnt/d/ps26172/model/train/run_v4.sh
set -euo pipefail
cd /mnt/d/ps26172
PY=~/.venvs/ps26172/bin/python
A=model/artifacts/v4
mkdir -p "$A"
export TF_CPP_MIN_LOG_LEVEL=2
echo "dataset start $(date -Is)"
$PY model/data/build_dataset.py --out ~/ps26172_data/ds_v4 --tts-root ~/ps26172_data/tts_v2 --long-negatives \
    --extra-beds bed_train_v4 --continuation 0.5 --session-negatives session_negatives_v4 > "$A/dataset.log" 2>&1
echo "train start $(date -Is)"
$PY model/train/train.py --data ~/ps26172_data/ds_v4 --run v4 --pos-weight 4 > "$A/train.log" 2>&1
echo "export start $(date -Is)"
TF_CPP_MIN_LOG_LEVEL=3 $PY model/train/export.py --run v4 --data ~/ps26172_data/ds_v4 > "$A/export.log" 2>&1
echo "done $(date -Is)"
