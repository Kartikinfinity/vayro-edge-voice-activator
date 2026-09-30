# Software Stack and Development Environment {#ch-software .chapter}

## Four environments

The project runs in four software environments on one PC. Knowing which is which explains most of the file layout.

Table: The four environments {#tab-envs}
| Environment | Where | Used for | Python |
|---|---|---|---|
| Firmware toolchain | Windows, `D:\esp\esp-idf-v5.5.5`, tools in `D:\esp\.espressif` | building and flashing the ESP32-S3 firmware | CPython 3.12 (IDF's own virtual environment) |
| Training environment | WSL2 Ubuntu, virtual env `~/.venvs/ps26172` | dataset building, training, int8 export, offline evaluation, the host-twin front end | CPython 3.12.14 via uv 0.12.19 |
| Host tools | Windows, `D:\ps26172\.venv-host` | capture tool, analysis, report figures, forbidden-dependency gate, code generators | CPython 3.12 |
| ASR server | Windows, the same `.venv-host` + vosk | the ingest server and its analysis scripts | CPython 3.12 |

Why two operating systems? ESP-IDF builds natively on Windows; TensorFlow's CPU build and the host-twin C library are simplest on Linux. The repository lives at `D:\ps26172` because ESP-IDF cannot build from a path containing a space (`D:\sih final` has one, DEC-02), and the IDF wrapper forces Python 3.12 because the PC's default Python 3.14 broke IDF's environment script. [VERIFIED — `tools/idf.ps1`, memory note]

## Firmware toolchain and libraries

Table: Firmware software with verified versions {#tab-fwsw}
| Component | Version | Licence | Purpose | Source of the version |
|---|---|---|---|---|
| ESP-IDF | **v5.5.5** (git tag) | Apache-2.0 | RTOS, drivers, Wi-Fi, TCP/IP, build system | `@BOOT idf=v5.5.5`, `dependencies.lock` [VERIFIED] |
| Xtensa GCC | **14.2.0** | GPL (tool only) | compiler | `CMakeCCompiler.cmake` in the build folder [VERIFIED] |
| CMake | 3.30.2 | BSD | build | path in the build log [VERIFIED] |
| esptool | 4.12.0 | GPL-2.0+ (tool only) | flashing, chip identification | logs [VERIFIED] |
| FreeRTOS | as shipped in IDF 5.5.5 (SMP) | MIT | tasks, queues, run-time statistics | [VERIFIED] |
| lwIP | as shipped in IDF 5.5.5 | BSD-3 | TCP/IP | [VERIFIED] |
| esp_wifi / esp_phy / esp_coex | as shipped in IDF 5.5.5 | **Espressif binary licence (closed)** | Wi-Fi radio | link map, SBOM [VERIFIED] |
| esp-tflite-micro | **1.4.1** (component hash `bdb2625e…`) | Apache-2.0 | TensorFlow Lite Micro interpreter | `firmware/dependencies.lock` [VERIFIED] |
| esp-nn | **1.4.1** (component hash `3b3411b0…`) | Apache-2.0 | optimised int8 convolution kernels for the S3 | `dependencies.lock` [VERIFIED] |
| TFLM microfrontend | tflite-micro commit `aab6e2fd` (vendored, unmodified) | Apache-2.0 | log-mel feature extraction | `firmware/components/microfrontend/PROVENANCE.md` [VERIFIED] |
| KissFFT | from esp-tflite-micro v1.4.1, commit `5d505b5f` | BSD-3-Clause | the FFT inside the microfrontend (16-bit fixed point) | `PROVENANCE.md` [VERIFIED] |

**How the versions are pinned.** `firmware/main/idf_component.yml` requests `espressif/esp-tflite-micro: "==1.4.1"`; the ESP component manager resolves that to esp-nn 1.4.1 and records both with content hashes in `firmware/dependencies.lock`. The study warned why this matters: an unpinned esp-nn update once enlarged the tensor arena needed on the S3 and broke a working wake-word product (X7). The microfrontend is *copied into the repository* because esp-tflite-micro 1.3.3.1 to 1.4.1 do not include it (C-03). [VERIFIED]

**Build configuration layers.** `tools/idf.ps1` assembles the configuration from several files, in order: `sdkconfig.defaults` (policy: 240 MHz, PSRAM off, 1 kHz tick, run-time stats, performance optimisation, cache sizes, heap hooks) → `sdkconfig.board` (pins, I2S framing) → `sdkconfig.console_<uart|usbjtag>` → `sdkconfig.model` (generated operating point) → `sdkconfig.wifi` (local credentials, git-ignored) → an optional extra file such as `sdkconfig.product`. It also regenerates the `sdkconfig` whenever any of these is newer, because ESP-IDF otherwise silently ignores a changed defaults file. [VERIFIED]

## Training environment

Table: Training software (from `model/env/requirements.lock`, 47 pinned packages) {#tab-trainsw}
| Package | Version | Purpose |
|---|---|---|
| tensorflow (CPU) | 2.21.0 | training and int8 conversion (also recorded in every `metrics.json`) |
| keras | 3.15.1 | model definition |
| numpy / scipy | 2.5.3 / 1.18.1 | signal processing, mixing, filters |
| soundfile | 0.14.0 | reading FLAC/WAV |
| piper-tts | 1.8.0 (GPL-3.0, run as a separate tool) | generating synthetic keyword audio |
| onnxruntime | 1.30.0 | Piper's neural voice runtime |
| matplotlib | 3.11.2 | plots |

Data assets used by training: four Piper voices (`en_US-libritts_r-medium`, `en_GB-vctk-medium`, `en_US-l2arctic-medium`, `hi_IN-pratham-medium`, 63–79 MB each, downloaded 27 Sep) and LibriSpeech `dev-clean`. The host-twin library `libpsfe.so` is compiled in WSL with the system `gcc -O2` from the same C files as the firmware (`model/frontend/build_twin.sh`); the Ubuntu release and host gcc version were not recorded. [VERIFIED except the last point, UNVERIFIED]

## Host tools and server

Table: Host and server software {#tab-hostsw}
| Package | Version | Used by |
|---|---|---|
| Python | 3.12 | all host tools and the server |
| numpy / scipy / matplotlib | 2.5.3 / 1.18.1 / 3.11.2 | capture analysis, server audio conditioning and VAD, report figures |
| pyserial | 3.5 | `host/capture.py` (USB link) |
| vosk | 0.3.45 (Apache-2.0) | speech recognition in `server/ingest.py` |
| vosk-model-en-in-0.5 | 971 186 187 B zip, SHA-256 `0365c52f…` | final ASR model (Indian English; publisher's WER 36.12 %) |
| vosk-model-small-en-in-0.4 | 37 573 330 B zip | first ASR model (publisher's WER 49.05 %), replaced 28 Sep |

Sources: `docs/SBOM.md`, `docs/PROJECT_STATE.md` §6. [DOCUMENTED]

## How the pieces talk to each other

!fig #fig-moddeps figures/module_deps.svg | Firmware components and their dependencies. Four source files are generated from the model and front-end definitions before every build. | 100

The software stack is linked by four **generated files** and two **wire formats**, and understanding these is the quickest way into the code:

- `model/frontend.json` → `tools/gen_frontend_config.py` → `ps_frontend_config.h` (firmware) — and the same JSON is read at run time by `model/frontend/psfe.py` (training).
- The host twin's maths tables → `model/frontend/export_tables.py` → `ps_frontend_tables.c` (firmware).
- A trained model folder `model/artifacts/<run>/` → `tools/gen_model_source.py` → `model_data.c` (model bytes, SHA-256s, input lookup table) and `sdkconfig.model` (threshold, averaging, stride, refractory).
- The **USB frame format** (`serial_link.h`) connects the firmware to `host/capture.py`.
- The **TCP stream format** (`netstream.h`) connects the firmware to `server/ingest.py`.

## Compliance tooling

- `tools/forbidden_deps.py` scans every source, manifest and lock file for ESP-SR, WakeNet, MultiNet, `srmodels.bin`, Picovoice/Porcupine, Sensory, Cyberon, Alango and known pre-trained wake-word model names, and fails the build on any hit. It runs before every firmware build. [VERIFIED]
- `docs/SBOM.md` lists every component, version and licence, discloses the closed Wi-Fi/PHY libraries, the GPL tools that are *run* but not linked (esptool, piper-tts), and two training voices whose datasets are licensed non-commercially (L2-ARCTIC, Pratham). [VERIFIED]
- The project's own code is Apache-2.0 (`LICENSE`, team decision 29 Sep). [VERIFIED]

## Versions that could not be confirmed

WSL Ubuntu release; the host gcc used for `libpsfe.so`; the exact FreeRTOS and lwIP versions bundled in IDF 5.5.5 (not printed anywhere in the logs); the Wi-Fi router's firmware. None affects a measured result, but they are listed so that no version in this report is guessed. [UNVERIFIED]
