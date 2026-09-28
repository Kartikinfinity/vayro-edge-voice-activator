# PS26172 — Project State Record

**Last updated:** 2026-09-26 ~21:00 (local) · **Internal deadline:** 2026-09-29 EOD · **Official:** 2026-09-30 (contingency only)

This file is operational memory. It never overrides the source documents in §1.

## 1. Sources

| Source | Location | Version / SHA-256 prefix | Status |
|---|---|---|---|
| SIH PS 26172 (problem statement) | `D:\sih final\sih 2026  (1).pdf` | 1 page · `c1a641b99c977b2e` | Read in full — **binding** |
| Track C hardware architecture | `D:\sih final\PS26172_TRACK_C_HARDWARE_ARCHITECTURE.md` | dated 2026-09-12 · 1 811 lines · `3855643469453cef` | Read in full — **primary technical direction** |
| Master Spec, Track A, Track B | referenced throughout the architecture | — | **NOT PROVIDED.** Their IDs (AMB-/NFR-/ASM-/F-/I-) are used only as the architecture quotes them. |
| Official SIH submission guidelines / PPT template | — | — | **NOT PROVIDED.** Needed before fixing PPT format, video length, naming. |

## 2. Mandatory requirements (from the PS only)

| ID | Requirement [SIH] |
|---|---|
| R1 | Lightweight, accurate KWS model running **locally** on a low-power device |
| R2 | On detection, stream the **subsequent audio** to a **remote ASR server** with minimal data overhead and latency |
| R3 | Judged on: efficiency (model RAM/flash, idle CPU), accuracy (high TPR, near-zero false activations), latency (keyword end → cloud ASR receiving the stream) |
| R4 | Open-source only; proprietary / closed / commercial **voice-activation SDKs prohibited** |
| R5 | KWS pipeline built on open-source ML/TinyML frameworks (e.g. TFLite Micro) |
| R6 | No models pre-trained on generic assistant keywords; training on a **custom keyword** |
| R7 | Edge software **< 256 KB RAM** and **< 10 % CPU** while idling in continuous listening |
| R8 | Heavy/uncompressed pre-trained transformers disqualified |
| R9 | Evaluated on a physical low-power microcontroller (e.g. Raspberry Pi, ESP32) |
| R10 | Model must work for the given custom keyword |

## 3. Locked technical direction (architecture "ARCHITECTURE DECISION" — not re-litigated)

Architecture **A spine, measurement-gated promotion to B**. ESP32-S3 @240 MHz, PSRAM disabled · INMP441 on I2S0, 16 kHz, 32-bit × 2 slots, BCK 1.024 MHz (Path α) · int16 from bits 23:8 · microfrontend 30 ms / 10 ms / 40 mel / 125–6 500 Hz / NR + PCAN / int8 · 1D DS-CNN streaming INT8, TFLM + esp-nn, random init · inference every 30 ms, window-5 mean, threshold 0.95, 2 s refractory · 1.0 s unified ring, 3 cursors · warm TCP from boot, PCM16, 20 ms frames, 8-byte header · self-hosted ingest + Vosk/Kaldi · **no ESP-SR anywhere** (X25).

## 4. Implementation decisions (this project)

| ID | Decision | Evidence / reason |
|---|---|---|
| DEC-01 | Toolchain = **ESP-IDF v5.5.5** (native, git tag), tools in `D:\esp`. Not PlatformIO `espressif32 7.1.1`, which pins IDF 6.1 + GCC 15. | esp-tflite-micro v1.4.1 manifest requires IDF ≥ 5.1 [LIB, read 2026-09-26]; the IDF 5.x line is what the architecture's reference deployments ran on. Installed OK 2026-09-26 20:37. |
| DEC-02 | Repository at `D:\ps26172` | ESP-IDF does not support spaces in project paths; `D:\sih final` has one. |
| DEC-03 | M1 debug/data link = CRC-framed USB serial, not TCP | Isolates mic/I2S faults from Wi-Fi faults; the same tool records training and held-out audio through the real mic (X16/X17). Product streaming remains TCP (M5). |
| DEC-04 | M1 capture carries the full 24-bit sample; the host derives int16 with the identical shift (I2S word >> 16) | Keeps the int16 level decision (C-07) open until speech level is measured. |
| DEC-05 | Unified ring (§8.4) built at M2, not M1 | Its first consumer is the front end. |
| DEC-06 | **I2S RX framing = MSB-justified** (not Philips as in §2.2/P-02), normal BCK edge | Measured (E-18): Philips captures one bit late (LSB never set, sign bits leak into the empty slot); MSB is bit-aligned. Locked in `firmware/sdkconfig.board`. |
| DEC-07 | Console/capture link = native USB-Serial-JTAG (COM7); firmware waits for a host start byte before starting I2S | The board's USB port is the native one (VID 303A:1001). Without the start byte, boot diagnostics are lost before the host opens the port. |
| DEC-08 | **Keyword = "Hey Vayro"**, pronounced "Hey VAI-ro" (3 syllables) | User decision 2026-09-27; satisfies §B8 (3–4 syllables). "Vayro" alone was offered and declined. |
| DEC-09 | int16 conversion stays **bits 23:8 (word >> 16)** as §2.4 specifies — C-07 closed without an architecture change | E-06: in-band room floor ≈52 LSB RMS, int16 quantisation noise ≈45 dB below it. The level offset versus training corpora is handled with gain augmentation over the measured range plus real recordings through this mic. |
| DEC-10 | MIC_SETTLE stays **300 ms** — C-11 withdrawn | E-19: the front-end band settles within 100 ms after clock start (cold and warm); the long DC tail is below 125 Hz. |
| DEC-11 | **Deviation (user-approved 2026-09-27):** the submission build runs a **windowed** causal 1D DS-CNN (last ~1 s of features, every ~60 ms) instead of the stateful streaming model in §7.1/§11-A. Streaming conversion becomes a PROPOSED roadmap item. | Deadline risk: stateful int8 streaming in TFLM is the least-proven step. Same causal, no-padding architecture (X5 rule), so the weights convert later without retraining. Cost: inference CPU [EST] 3–7 % of one core versus ≈1 %; to be MEASURED in EXP-2 and reported against the 10 % gate. |
| DEC-12 | Training environment = WSL Ubuntu, uv-managed CPython 3.12 venv (`~/.venvs/ps26172`), TensorFlow CPU, Piper TTS; public negatives = LibriSpeech dev-clean | User-approved downloads 2026-09-27. Script `tools/setup_train_env.sh`; versions frozen to `model/env/requirements.lock`. |
| DEC-13 | Ambient recording: afternoon (~13:30–18:00) + overnight, through this mic | User-approved 2026-09-27, including household sound. Local only, used only as non-keyword data. |
| DEC-14 | TTS input text = **"Hey Vyro"** (English voices) and **"हे वाइरो"** (Hindi voice); the keyword itself is unchanged | espeak-ng phonemes via Piper (`model/data/tts_probe.py`): "Hey Vayro" → /veɪɹoʊ/ (wrong, VAY-ro) in all 3 English voices; "Hey Vyro" → /vaɪɹoʊ/ ✓; "हे वाइरो" → /ʋaːɪɾoː/ ✓. Human listening check pending. |
| DEC-16 | **Canonical front-end tables:** the host twin's filterbank weights/unweights and PCAN gain LUT are exported (`model/frontend/export_tables.py` → `ps_frontend_tables.c`) and copied into the device state after `ps_fe_init()`. Applied only if their recorded frontend.json SHA-256 matches. | M2 parity found 3 values in 3 of 5 998 frames differing (bands 34–35). The table-hash diagnostic (`@FETAB`) showed **fb_weights (log1pf) differ** between newlib and glibc; the PCAN LUT pre-fix comparison was inconclusive because its hash then included uninitialised LUT slots (fixed). After the fix: 8/8 table hashes EQUAL and features bit-exact (12 000/12 000 and 3 001/3 001 frames). |
| DEC-17 | Model export uses a **static batch-1 graph** (`model/train/export.py`): ops = CONV_2D, DEPTHWISE_CONV_2D, RESHAPE, FULLY_CONNECTED, LOGISTIC | Keras 3 `Flatten`/`Reshape` with a dynamic batch emitted SHAPE/STRIDED_SLICE/PACK. The static export gives identical posteriors (verified on S01). |
| DEC-18 | Model selection needs a **real-speech validation set separate from the test set** | v1 beat v0 on synthetic validation (PR-AUC 0.949 vs 0.929) but was worse on real speaker S01 (18/23 vs 22/23 at thr 0.9). Choosing by S01 would be test-set selection. |
| DEC-19 | **v2 data split:** S01 session 1 → training; S01 session 2 → validation (selection only); held-out test = ambient c002, overnight ambient, and any session/speaker recorded after v2 is frozen. Selection rule declared before results: `model/artifacts/selection_rule_v2.json` (FA-first lexicographic). | Only one real speaker is available (S02 not recorded). Speaker-independent evidence so far = v0 on S01 (TTS-only training). |
| DEC-20 | Recording protocol **v2**: 4 s utterance windows plus a "next:" preview 1.2 s ahead (`host/scripts/kw_session_v2.txt`); evaluation adds a label-free **prompt score** | Session 2: utterances drifted to the window end and into the next prompt, so energy labels attributed detections to the wrong prompt (labeller recall 15/25 vs prompt recall 20/25 for v0). |
| DEC-21 | M5 transport as specified (§9.2/§9.3): Wi-Fi STA, one warm TCP connection from boot, TCP_NODELAY, 8-byte header (fixed payload size per packet type, since §9.3 has no length field), 2 × 20 ms PCM16 per packet, 624 ms pre-roll from the unified ring, server END + 10 s device timeout + OVERRUN marker, NTP-style clock pings (lowest-RTT of the last 8). **Wi-Fi modem sleep disabled** (Kconfig) for symmetric, low latency. | Credentials only in the gitignored `firmware/sdkconfig.wifi`. Server: `server/ingest.py`. Network build compiles (image 926 247 B); app partition enlarged to 1.5 MB. |
| DEC-22 | **Product configuration** `firmware/sdkconfig.product` (EXP-1): ring 1.0 → **0.75 s** and pre-roll 624 → **571 ms** (§8.3 contingency row "window 5", triggered by measured detection lag ≤ 144 ms < 221 ms), arena 16 KiB, no capture streams or link TX task, static Wi-Fi RX buffers 4 (§B4 said 6), §B4 dynamic buffer/lwIP trims, Wi-Fi/FreeRTOS/ringbuf/heap code out of IRAM, zero-copy model input, reader stack 3584 | First product build measured S4 = 260.2 KiB (over 256 KiB). After these changes: 238.1 KiB (non-streaming peak). The 0.75 s ring leaves 179 ms of slack at trigger (vs 376 ms), measured once streaming works. |
| DEC-23 | v3 (hard negatives + night beds) selected at thr 0.60 by its declared rule; **ship decision pending** the new active-household recording (`selection_rule_v3.json`) | S01 s3 test: v3 23/25 & 3/16 vs v2b 22/25 & 2/16; night held-out 5 h: 1 FA each. |
| DEC-15 | Front end = TFLM microfrontend **vendored unmodified** (tflite-micro `aab6e2fd`, KissFFT from esp-tflite-micro v1.4.1), wrapped by `ps_frontend.c`; every parameter set explicitly from `model/frontend.json` (SHA-256 `5bd00bc673ecb2b3…`) | Resolves C-02/C-03. The same sources build the firmware and the host twin (`model/frontend/libpsfe.so`). Upstream defaults differ from §7.2 (25 ms window, PCAN off), so none are relied on. |

## 5. Conflicts and open issues

| ID | Issue | Practical effect / proposed handling |
|---|---|---|
| C-01 | Architecture programme is 3 weeks (§B10) + 12 experiments; ~3 days remain | Compressed plan (§7) with explicit descoping; descoped items stay PROPOSED in the PPT roadmap. |
| C-02 | §7.2/§B3 specify microfrontend **and** an esp-dsp float real-FFT. Upstream TFLM microfrontend computes its FFT internally with fixed-point KissFFT (`kiss_fft_int16`) [LIB, verified 2026-09-26] | The two cannot both hold without breaking §7.3 bit-exact parity. Proposed at M2: keep microfrontend unmodified (parity wins) and measure its CPU; defer the esp-dsp FFT. |
| C-03 | esp-tflite-micro v1.3.3.1 / v1.3.8 / v1.4.0 / v1.4.1 contain **no** microfrontend sources (the CMake glob hits an absent directory) [LIB, verified] | Vendor microfrontend from upstream tflite-micro (Apache-2.0), pinned by commit, at M2. |
| C-04 | Mel upper edge 6 500 Hz (O1) vs 7 500 Hz in the microWakeWord/ESPHome reference pipeline [to verify at M2] | If mWW training code is reused, its feature generation must be set to the same `frontend.json`. |
| C-05 | §B5 pin map (GPIO 4/5/6) vs the existing, working wiring | Firmware follows the real wiring via `firmware/sdkconfig.board`; no rewiring. Pins **pending**. |
| C-06 | GPIO duty-cycle (I-1) needs a logic analyser; IN-1 playback rig needs a host GPIO | If unavailable: systimer (I-2) + FreeRTOS run-time stats (I-3) become the primary CPU evidence and are labelled as such. |
| C-07 | **Level risk (new).** §2.4 fixes int16 = bits 23:8; its own estimate (speech @1 m ≈ −60 dBFS [EST]) implies ~30 LSB RMS in int16, while TTS/public training audio sits near −20…−30 dBFS | Measure the real speech level at M1. Fix the shift/gain **before** training (changing it later forces a retrain). |
| C-08 | Board variant unknown | §3.7 already covers PSRAM-equipped modules (PSRAM disabled). Octal PSRAM (R8) makes IO35–37 unavailable. |
| C-09 | Keyword not chosen (PS: "the given custom keyword") | Blocks positive-data recording and M3. Does not block M1. |
| C-10 | **IRAM code is missing from the §3.4 SRAM budget (new, measured).** The M1 build already places **60 015 B of code in internal SRAM** (DIRAM `.text`, linker report `evidence/m0/size_uart_m1build.txt`). Wi-Fi/lwIP add more IRAM code by default. Under the strictest S4 reading ("total device SRAM occupancy") this counts. | At EXP-1, report S4 both with and without IRAM code. Apply IDF flash-placement options (Wi-Fi/lwIP IRAM optimisations off, FreeRTOS/ringbuf/heap functions into flash) and measure their CPU cost. This could move the §3.5 headroom (29.7 KiB [EST]) to negative. It is the most important thing EXP-1 must settle. |

| C-11 | **MIC_SETTLE = 300 ms (from P-19) is too short on this hardware.** After every I2S clock start the output carries a DC/LF transient of up to 27 % FS that takes ~1–2 s to settle (E-19, warm boots) | Proposed: set MIC_SETTLE from the measured settle time (cold boot pending), roughly 2–3 s, once per boot. The clock never stops afterwards, so this costs nothing at runtime. |
| C-12 | Room LF energy: steady 0–125 Hz ≈ −30 dBFS (peak lines 61–70 Hz); speech band −47 dBFS with nobody speaking to the mic | Likely airflow (fan) plus background sound; room conditions not yet recorded. It uses headroom, so it constrains the int16 gain decision (C-07); the 125 Hz mel floor keeps it mostly out of the features. |

## 6. Hardware and host

| Item | State |
|---|---|
| ESP32-S3 board | ESP32-S3 (QFN56) **rev v0.2**, **embedded 8 MB PSRAM (AP_3v3)**, **16 MB quad flash**, MAC e0:72:a1:xx:xx:xx — from esptool eFuse/flash read (`evidence/m1/esptool_flash_id.txt`). Native USB-Serial-JTAG on **COM7**. PSRAM disabled in sdkconfig (§3.7). Firmware `esp_chip_info()` reports `emb_psram=0` and `flash_bytes` = the configured 4 MB; the esptool read is authoritative. |
| Pre-existing firmware | Arduino-ESP32 sketch (IDF v4.4.7, built 2024-03-05, 16 MB OTA layout), backed up in full: `D:\ps26172_backup\preexisting_flash_16MB.bin`, SHA-256 `56a88cea8d0d8f7d…` |
| INMP441 | SCK→GPIO6, WS→GPIO5, SD→GPIO4, L/R→GND, VDD→3V3 (user-reported). Measured: mic on the LEFT slot; empty slot reads 100 % zero (SD held low, consistent with P-07). |
| Logic analyser · 2.4 GHz AP for demo | **unknown** |
| Host PC | i3-8100 (4 cores), 15.9 GB RAM, no GPU, Windows 11, Python 3.11/3.12/3.13/3.14, WSL2 Ubuntu available |
| Host tools | `.venv-host` (Python 3.12): numpy 2.5.3, scipy 1.18.1, matplotlib 3.11.2, pyserial 3.5 |

## 7. Compressed plan

| When | Milestones | Exit evidence |
|---|---|---|
| 26 Sep night | M0 toolchain + X25 gate · **M1 physical audio** · start overnight ambient recording through the INMP441 | build log · WAV + PSD + level + DIAG · capture integrity |
| 27 Sep | Keyword positives (TTS + real speakers) · M2 front end + parity test · M3 train + deploy | parity PASS · posterior rises on the keyword |
| 28 Sep | M4 trigger / refractory / instrumentation · M5 warm-TCP streaming + ingest · M6 Vosk · EXP-1 memory · EXP-2 CPU · latency · overnight false-activation exposure | logs, CSVs, plots from saved data |
| 29 Sep | Evidence pack → PPT → demo video | — |

**Descoped for submission (stay PROPOSED):** Architecture-B promotion and 3-model DET comparison (EXP-8), EXP-3/3b/4/9/12, ADPCM (EXP-6), IN-1 hardware playback rig, Architecture C (speculative streaming, UDP), bounded-heap *enforcement* (reporting kept).

## 8. Milestone status

| Milestone | Status |
|---|---|
| M0 toolchain, pinned build, X25 gate | **DONE** 2026-09-26 — ESP-IDF v5.5.5; `tools/idf.ps1 -Console uart build` green, gate PASS, image 241 095 B |
| M1 physical audio | IN PROGRESS — flashed and running; alignment fixed (DEC-06); EXP-10 done; **scripted cold-boot Session A (user) and 10 min integrity run pending** |
| M2 front end + parity | **DONE** 2026-09-27 — bit-exact device vs host features after DEC-16 (runs `…145754`, `…150156`) |
| M3 local KWS | **ON DEVICE** — v0 (windowed DS-CNN, 10 665 params, 212 584 MACs, 28 024 B int8) runs on the ESP32-S3 via esp-tflite-micro 1.4.1 + esp-nn 1.4.1; device outputs bit-exact with host TFLite reference (1 984/1 984). Offline on held-out real speaker S01: 22/23 at thr 0.9, N=3. **Live spoken test pending.** |
| M4 trigger | Decision logic (N-mean, threshold, 2 s refractory, IN-2 GPIO 15 pulse, `@KW` log) implemented on device; exit test pending (live keywords) |
| M4 trigger | **DONE (software instruments)** — live triggers exactly equal the offline decision replay (E-26, re-confirmed on session 3). GPIO pulse present but not captured (logic analyser arrives 28 Sep). |
| M5 streaming | **DONE** 2026-09-27 — 24/24 detections streamed with pre-roll, 0 overruns, 0 seq gaps (E-36); L1 median 1.66 ms, L2 ≈ 95 ms median (E-37). |
| M6 ASR | NOT STARTED |
| **Open risk** | Evening acoustic domain (E-34): the room is 10–15 dB louder at 5–8 kHz in the evening. Its effect on recall is **untested**; next: a fresh scripted session (S01 s3, test data) under evening conditions with streaming on. |

## 9. Blockers

Training toolchain not installed (WSL Python is 3.14; TensorFlow needs ≤ 3.13) · real keyword recordings not yet made

Room conditions for Session A (user, verbatim): "fan was on of other room sound i could listen pc is about 30 cm from mic".

## 10. Next task

Record real "Hey Vayro" sessions (`host/scripts/kw_session_v1.txt`, one run per speaker). Then afternoon ambient recording, M2 front end and training setup, and the overnight ambient run.
