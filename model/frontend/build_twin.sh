#!/usr/bin/env bash
# Builds the host twin of the firmware front end from the SAME vendored C sources
# (firmware/components/microfrontend) into model/frontend/libpsfe.so. Run inside WSL.
set -euo pipefail
REPO=/mnt/d/ps26172
C=$REPO/firmware/components/microfrontend
OBJ=$HOME/ps26172_build/psfe
rm -rf "$OBJ" && mkdir -p "$OBJ"
INC="-I$C -I$C/include -I$C/kissfft"
for f in "$C"/ps_frontend.c "$C"/tensorflow/lite/experimental/microfrontend/lib/*.c; do
  gcc -O2 -fPIC -std=gnu17 $INC -c "$f" -o "$OBJ/$(basename "$f").o"
done
for f in "$C"/*.cc "$C"/tensorflow/lite/experimental/microfrontend/lib/*.cc; do
  g++ -O2 -fPIC -std=gnu++17 $INC -c "$f" -o "$OBJ/$(basename "$f").o"
done
g++ -shared -o "$REPO/model/frontend/libpsfe.so" "$OBJ"/*.o -lm
echo "built $REPO/model/frontend/libpsfe.so ($(gcc --version | head -1))"
