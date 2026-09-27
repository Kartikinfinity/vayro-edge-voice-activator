# microfrontend component — provenance

| Part | Source | Pin | Licence |
|---|---|---|---|
| `tensorflow/lite/experimental/microfrontend/lib/*` (excluding tests, `*_io.*`, `*_main.c`, `*memmap*`, BUILD, README) | https://github.com/tensorflow/tflite-micro | commit `aab6e2fdb1b22e424395939462d30ac1bb5d950c` (2026-09-25) | Apache-2.0 (`LICENSE.tflite-micro`) |
| `kissfft/*` | https://github.com/espressif/esp-tflite-micro `third_party/kissfft` | tag v1.4.1, commit `5d505b5ffac8e60923bf29a0cc6e6348c84e3763` | BSD-3-Clause (`kissfft/COPYING`) |
| `ps_frontend.c`, `include/ps_frontend.h` | this project | — | project |
| `include/ps_frontend_config.h` | GENERATED from `model/frontend.json` by `tools/gen_frontend_config.py` | SHA-256 of the JSON embedded | project |

Vendored files are unmodified. The same files build the host twin (`model/frontend/build_twin.sh`).
