#!/usr/bin/env bash
# Piper TTS voices for synthetic keyword positives (approved 2026-09-27; source HF rhasspy/piper-voices).
set -euo pipefail
VENV=$HOME/.venvs/ps26172
DIR=$HOME/ps26172_data/piper_voices
mkdir -p "$DIR"
cd "$DIR"
for v in en_US-libritts_r-medium en_GB-vctk-medium en_US-l2arctic-medium hi_IN-pratham-medium; do
  [ -f "$v.onnx" ] || "$VENV/bin/python" -m piper.download_voices --data-dir "$DIR" "$v"
done
ls -la "$DIR"
sha256sum "$DIR"/*.onnx
"$VENV/bin/python" -c "import importlib.metadata as m; print('piper-tts', m.version('piper-tts'))"
