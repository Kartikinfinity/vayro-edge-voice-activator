# PS26172 — Software Bill of Materials and licence disclosure

Status 28 Sep 2026. Versions are the pinned ones (`firmware/dependencies.lock`, `model/env/requirements.lock`, host venv).
R4/R5 check: **no proprietary voice-activation SDK anywhere**. ESP-SR / ESP-Skainet / WakeNet / vendor KWS are excluded by an
automated build gate (`tools/forbidden_deps.py`, X25), which runs on every `tools/idf.ps1` build.

## 1. Edge firmware (runs on the ESP32-S3 — the judged software)

| Component | Version | Licence | Role | Notes |
|---|---|---|---|---|
| ESP-IDF | v5.5.5 | Apache-2.0 (FreeRTOS kernel MIT, lwIP BSD-3-Clause, mbedTLS Apache-2.0, newlib BSD-style) | RTOS, drivers (I2S, GPIO, USB-Serial-JTAG), TCP/IP | open source |
| **Wi-Fi / PHY libraries** (`esp_wifi`, `esp_phy`, `esp_coex` binaries inside ESP-IDF) | with IDF v5.5.5 | Espressif binary licence (closed source) | Wi-Fi MAC/PHY only | **Disclosed residual blob** (architecture §6.5): a radio driver, not a voice SDK; no part in audio, features, KWS or the decision. The KWS ran with networking disabled before M5 (`-NoNet` build) |
| esp-tflite-micro | 1.4.1 | Apache-2.0 | TensorFlow Lite Micro interpreter | open source (TinyML framework, R5) |
| esp-nn | 1.4.1 | Apache-2.0 | optimised int8 conv / depthwise kernels | open source |
| TFLM microfrontend | tflite-micro commit `aab6e2fd`, vendored unmodified | Apache-2.0 | log-mel front end (window, FFT, filterbank, noise reduction, PCAN, log) | `firmware/components/microfrontend/PROVENANCE.md` |
| KissFFT | from esp-tflite-micro 1.4.1 | BSD-3-Clause | FFT used by the front end | |
| Project firmware (`firmware/main`, `firmware/components/*` except vendored) | this repo | **Apache-2.0** (`LICENSE`, chosen by the team 29 Sep) | capture, ring, front-end glue, KWS engine, decision logic, netstream | original work |
| KWS model **v2b** (DS-CNN, 10 665 params, 28 024 B int8) | sha256 `f7c913efdbb28f64…`, threshold 0.80 (DEC-26) | Apache-2.0, original work (see §4 for training-data terms) | keyword "Hey Vayro" | **trained from random initialisation**; no pre-trained wake-word or speech model used (R6) |

## 2. Remote ASR server (PC; not part of the edge budget)

| Component | Version | Licence | Role |
|---|---|---|---|
| Python | 3.12 | PSF | runtime |
| vosk (Kaldi-based ASR API) | 0.3.45 | Apache-2.0 | speech recognition (not a transformer — architecture §9.5) |
| vosk-model-en-in-0.5 | sha256 `0365c52f79308d81…`, 971 186 187 B zip | Apache-2.0 | primary ASR model (Indian English; publisher's WER 36.12 % on NPTEL) |
| vosk-model-small-en-in-0.4 | sha256 `20663dcac4d5cb78…`, 37 573 330 B zip | Apache-2.0 | earlier ASR model (publisher's WER 49.05 % on NPTEL) |
| numpy / scipy | 2.5.3 / 1.18.1 | BSD-3-Clause | ASR conditioning, VAD endpointing |
| `server/*.py` | this repo | Apache-2.0 | TCP ingest, clock sync, VAD endpoint, transcripts |

## 3. Host tools (PC)

| Component | Version | Licence | Role |
|---|---|---|---|
| pyserial | 3.5 | BSD-3-Clause | USB link to the device |
| esptool | bundled with ESP-IDF v5.5.5 | GPL-2.0-or-later | flashing, reset (tool only, not linked into firmware) |
| `host/*.py` | this repo | Apache-2.0 | capture, prompts, analysis |

## 4. Training toolchain and data (offline; only the trained weights reach the device)

| Component / data | Version | Licence | Use | Disclosure |
|---|---|---|---|---|
| TensorFlow / Keras | 2.21.0 / 3.15.1 | Apache-2.0 | training, int8 conversion | |
| piper-tts | 1.8.0 | **GPL-3.0** | offline generation of synthetic keyword utterances | run as a separate tool; not linked into or shipped with any deliverable |
| Piper voice `en_US-libritts_r-medium` | HF rhasspy/piper-voices | dataset LibriTTS-R: CC BY 4.0 | synthetic positives | |
| Piper voice `en_GB-vctk-medium` | " | dataset VCTK: CC BY 4.0 | synthetic positives | |
| Piper voice `en_US-l2arctic-medium` | " | dataset L2-ARCTIC: **CC BY-NC 4.0** | synthetic positives (accented English) | **non-commercial** |
| Piper voice `hi_IN-pratham-medium` | " | **CC BY-NC-SA 4.0** | synthetic positives (Hindi-accented) | **non-commercial, share-alike** |
| LibriSpeech dev-clean | OpenSLR 12 | CC BY 4.0 | negatives (speech) | |
| Real recordings (speaker S01, room ambient, household) | recorded 26–28 Sep 2026 | project data, recorded with the household's consent | positives, hard negatives, evaluation | kept local; not redistributed |

**Training-data disclosure.** Part of the synthetic keyword audio comes from two voices trained on non-commercial datasets
(L2-ARCTIC, Pratham). This is compatible with a non-commercial competition entry. For commercial use the model should be
retrained without those two voices (`model/data/gen_tts.py` voice list); the pipeline is scripted, so this is a re-run, not a
redesign.

## 5. What is *not* used

ESP-SR, WakeNet, MultiNet, ESP-Skainet, Picovoice/Porcupine, Snowboy, Sensory, any cloud speech API, any pre-trained keyword
or speech-embedding model on the device, any transformer (edge or server).
