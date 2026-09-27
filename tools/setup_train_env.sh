#!/usr/bin/env bash
# PS26172 training environment (WSL Ubuntu). Approved downloads 2026-09-27:
#   uv + CPython 3.12 (astral.sh) · TensorFlow/numpy/scipy/soundfile/piper-tts (PyPI) · LibriSpeech dev-clean (openslr.org)
# Everything lands in $HOME (fast WSL filesystem); versions are frozen to model/env/requirements.lock.
set -euo pipefail
REPO=/mnt/d/ps26172
VENV=$HOME/.venvs/ps26172
DATA=$HOME/ps26172_data
mkdir -p "$DATA" "$REPO/model/env"

echo "[$(date -Is)] uv"
if [ ! -x "$HOME/.local/bin/uv" ]; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
UV=$HOME/.local/bin/uv
$UV --version

echo "[$(date -Is)] python 3.12 venv"
$UV python install 3.12
[ -d "$VENV" ] || $UV venv --python 3.12 "$VENV"

echo "[$(date -Is)] python packages"
$UV pip install --python "$VENV/bin/python" tensorflow numpy scipy soundfile piper-tts matplotlib
$UV pip freeze --python "$VENV/bin/python" > "$REPO/model/env/requirements.lock"
"$VENV/bin/python" -c "import tensorflow as tf, numpy, scipy; print('tensorflow', tf.__version__, '| numpy', numpy.__version__, '| scipy', scipy.__version__)"

echo "[$(date -Is)] LibriSpeech dev-clean"
cd "$DATA"
if [ ! -d LibriSpeech/dev-clean ]; then
  curl -L --fail -o dev-clean.tar.gz https://www.openslr.org/resources/12/dev-clean.tar.gz
  md5sum dev-clean.tar.gz | tee dev-clean.tar.gz.md5
  tar xzf dev-clean.tar.gz
fi
echo "LibriSpeech dev-clean flac files: $(find LibriSpeech/dev-clean -name '*.flac' | wc -l)"
echo "[$(date -Is)] DONE"
