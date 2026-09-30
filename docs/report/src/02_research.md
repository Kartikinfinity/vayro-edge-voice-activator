# The Research Foundation and How It Was Implemented {#ch-research .chapter}

## What was supplied, precisely

The project was started from two documents, both in `D:\sih final\`:

- **The problem statement** (`sih 2026  (1).pdf`, one page). It is the only *binding* source.
- **"PS26172_TRACK_C_HARDWARE_ARCHITECTURE"** (a 1 810-line Markdown study, dated 12 Sep 2026, written in the role of a "Principal Edge-Systems Architect"). This is the research document the implementation follows. It is not a peer-reviewed paper: it is an engineering research study that combines datasheet facts, numbers from open-source projects, published keyword-spotting literature (through a companion document called "Track B"), and its own calculations. [VERIFIED]

The study says it was written from three further documents — a "Master Spec", "Track A (evidence base)" and "Track B (technical intelligence)" — and from the ESP32-S3, ESP32-S3-WROOM-1 and INMP441 datasheets. **None of these was provided.** Their identifiers (AMB-01, ASM-07, F2, I9 …) appear in this report only as the study quotes them, and any fact the study attributes to them is at most [DOCUMENTED]. [VERIFIED — PROJECT_STATE.md §1 records the same]

The report also cites one external paper that nobody supplied: Zhang et al., "Hello Edge: Keyword Spotting on Microcontrollers" (arXiv:1711.07128, 2017), which introduced the depthwise-separable CNN (DS-CNN) family the final model belongs to. It is background, not a source of any number used here.

## The research problem the study addresses

The study's question is narrow and physical: *can an ESP32-S3 with an INMP441 microphone host a PS 26172-compliant system, where are the real limits, and how should it be proven?* Its central argument, inherited from Track B, is that PS 26172 is **"a false-activation problem wearing an accuracy problem's clothes"**: a wake word that fires on television speech is useless however well it scores on a benchmark. It therefore insists on measuring false activations per hour of real audio, not "accuracy". [VERIFIED — Track C, closing statement and §5.1]

## The study's method

The study is disciplined about the difference between *known* and *estimated*. Every statement carries a tag — [SIH] requirement, [HW] datasheet fact, [LIB] verified library fact, [ASM] assumption, [EST] estimate, [MEAS] measurement, [PROP] proposal — and it states plainly that it contains **zero measurements**. It then:

1. extracts the hardware facts with page citations (40 SoC facts H-01…H-40, 26 microphone facts P-01…P-26);
2. builds budgets before any code exists: memory in five nested scopes **S0–S4**, CPU in three scopes **C1–C3**, latency in three definitions **L1–L3**;
3. maps 12 candidate model families against the PS's real criteria (§5), and 10 runtimes against the open-source rule (§6);
4. proposes three complete architectures (A minimal-robust, B best trade-off, C lowest latency) and a trade-off matrix;
5. lists 25 failure modes (X1–X25), a 7-milestone plan (M0–M6) with binary exit criteria, and 12 experiments (EXP-1…EXP-12), several of them "kill conditions" that could invalidate the platform;
6. ends with a build blueprint: repository layout, subsystem split, configuration policy, pin map, data formats and boot sequence. [VERIFIED]

## Key technical principles in the study

This section explains the study's main ideas in plain language, because the whole implementation follows from them.

### The microphone sets hard rules

- **The INMP441 only speaks one I2S dialect.** It needs exactly 64 bit-clock pulses per stereo frame, so every sample travels in a 32-bit slot holding a 24-bit value. At 16 kHz the bit clock is 64 × 16 000 = **1.024 MHz**. There is no 16-bit mode, so the firmware must convert. (P-02, P-03)
- **Its low-pass filter scales with the sample rate.** The flat pass band ends at 0.423 × fs, which is **6 768 Hz at 16 kHz**. Standard keyword front ends use frequencies up to ~7.5 kHz, so the top bands would see a microphone roll-off that training audio does not have. The study's fix (option O1) is to stop the mel filterbank at **6 500 Hz** in both training and firmware. (P-16, §2.3b)
- **It has a fixed delay** of 17.2 samples (1.078 ms at 16 kHz), and outputs zeros for 2^18 clock cycles after power-up (≈ 256 ms), so the design includes a 300 ms `MIC_SETTLE` state. (P-15, P-19)

### Memory: the model is not the problem

The study's memory budget is its most important finding. Estimated peak use was about **227 KiB** without encryption. The model and its working memory were only **17 %** of that; the Wi-Fi driver, TCP/IP stack and operating system were **58 %**. Its advice: "optimisation effort should follow the bytes, not the intuition". It also argued that **PSRAM must be disabled** — using the board's extra 8 MB of external RAM would make the 256 KB limit meaningless — and that a TLS handshake at trigger time would break both the memory and the latency budget. [DOCUMENTED — Track C §3.5–§3.7; every number there is an estimate]

### CPU: use the vector unit and never ship reference kernels

The study estimated the whole always-on pipeline at **≈ 2.8 % of one core** at 240 MHz, with the FFT (the step that turns sound into frequencies) as the biggest single cost, and warned that forgetting the optimised kernels (esp-dsp for FFT, esp-nn for the network) would multiply the cost by 5–20×. It proposed measuring CPU three ways, with the MLPerf Tiny GPIO duty-cycle method as the primary instrument. [DOCUMENTED — §4]

### The model: shortlist, and train from scratch

After mapping 12 model families, the study concluded that CPU is not the discriminator on this chip — every candidate fits. What matters is whether TensorFlow Lite Micro has kernels for every operation, whether there is any false-activation evidence, and how much streaming state the model needs. It shortlisted a microWakeWord-style reference, a TC-ResNet8-style primary, and a dilated-convolution "false-activation hardened" model, to be compared on detection-error curves. It insisted on **training from random initialisation** so the PS's ban on pre-trained assistant keywords could never be argued. [DOCUMENTED — §5, §6.4]

### Compliance: two traps

- **ESP-SR / WakeNet**: Espressif's own speech SDK is one line of configuration away on this chip, is a vendor wake-word SDK with a "Custom" licence, ships binary models, and includes "Alexa" as a wake word — so it breaks three PS rules at once. The study required an **automated build gate** against it (failure mode X25). [DOCUMENTED — §6.3]
- **The Wi-Fi blob**: ESP-IDF is open source, but its Wi-Fi/PHY libraries are closed binaries. The study's position: this is a radio driver, not a voice-activation SDK, it is outside the KWS pipeline, and it must be **disclosed** in a software bill of materials rather than hidden. [DOCUMENTED — §6.5]

### Buffering: derive the pre-roll, share one ring

The device only fires *after* the keyword ends, so it must keep recent audio. The study derived the minimum stored audio as detection lag (≤ 374 ms) + 250 ms lead-in + 100 ms scheduling jitter = **724 ms**, rounded to a **1.0 s ring** (32 000 bytes), with pre-computed smaller rows for shorter smoothing windows (for a 5-score window: 571 ms in a 0.75 s ring). It also proposed a **single ring buffer with several read positions** instead of three copies, saving about 34 KB. [DOCUMENTED — §8.3, §8.4]

### Transport: open the connection at boot

Opening a TCP connection (and certainly a TLS session) when the keyword fires puts a network round trip on the measured path. The study chose **plain TCP opened at boot and kept warm**, 20 ms PCM frames, an 8-byte header, and an OVERRUN marker so that a stream the device could not keep up with ends short rather than corrupted. [DOCUMENTED — §8.5, §9]

### Latency: three definitions, because the PS is ambiguous

"The time delta between the keyword ending and the cloud ASR receiving the audio stream" can mean detection → server (**L1**), acoustic end of the keyword → first audio at the server (**L2**, the literal reading), or keyword end → the server holding audio up to real time (**L3**). The study instrumented all three and estimated **L1 ≈ 13 ms, L2 ≈ 205 ms**. [DOCUMENTED — §10]

### Decision logic and the refractory period

The study proposed averaging the last 5 scores with a 0.95 threshold, and — critically — a **2 s refractory period**: without it, one spoken keyword whose score stays high for 200 ms would produce six detections, and any false-activation count would be meaningless (X14). [DOCUMENTED — §8.6]

### The parity rule

A single JSON file defines the front end; the firmware compiles it, the training code reads it, and a "golden vector" test must show the device and the PC produce **bit-identical** features from the same audio. The file's hash is embedded so that a model trained with a different front end refuses to load. [DOCUMENTED — §7.3]

### The recommended architecture

The study's decision was **"Architecture A as the built spine, with a measurement-gated promotion path to Architecture B"**: build the shared skeleton (capture, front end, ring, transport, server, instrumentation) once, start with a small 1-D DS-CNN, and swap only the model and decision parameters if measurements justified it. Architecture C (speculative streaming, UDP) was not to be built. [DOCUMENTED — "Architecture decision"]

## Assumptions and constraints in the study

Table: The study's working interpretations of ambiguous PS wording {#tab-ambig}
| Ambiguity | Study's interpretation | What the implementation did |
|---|---|---|
| AMB-01: what "256 KB RAM" covers | strictest: peak total device SRAM — data, heap, stacks, network, DMA — with PSRAM off | measured "S4" = static internal RAM (incl. code in IRAM) + peak heap; checked against 256 000 B and 262 144 B [VERIFIED] |
| AMB-02: what "10 % CPU" means | duty cycle, per core and system-wide, mean and p99 over ≥ 10 min | FreeRTOS run-time stats per core and averaged, 12 min run; GPIO method not possible (no analyser) [VERIFIED] |
| AMB-06: latency end points | measure L1, L2, L3 | L1 and L2 measured; L3 not computed [VERIFIED] |
| AMB-09: scope of "open source only" | every firmware component OSI-licensed; disclose the Wi-Fi blob | SBOM discloses 9 closed Wi-Fi/PHY libraries + boot ROM [VERIFIED] |
| AMB-13/14: stream start and end | start before the keyword end; server ends the stream, device has a hard timeout | 571 ms pre-roll; server VAD sends END; 10 s device timeout [VERIFIED] |
| Hardware platform | ESP32-S3 is a choice, not a requirement; "the platform loses, not the requirement" | ESP32-S3 kept; EXP-1 did not trigger the kill condition [VERIFIED] |

## From research to implementation: the traceability table

This is the core of the chapter. For each important idea in the study: what it proposed, whether it was adopted, how, whether it changed, why, and how the result was checked.

Table: Research idea → implementation → validation {#tab-trace}
| # | Study proposal | Adopted? | How it was implemented | Change and reason | Validation |
|---|---|---|---|---|---|
| 1 | ESP32-S3 at 240 MHz, PSRAM disabled | Yes | `sdkconfig.defaults`: 240 MHz, `CONFIG_SPIRAM` not set; firmware prints `psram=disabled_in_sdkconfig` | board has 8 MB PSRAM in the package; left off as the study said | `@MEM`, `@BOOT emb_psram=0` in every run [VERIFIED] |
| 2 | INMP441 on I2S0, 32-bit × 2 slots, BCK 1.024 MHz, Philips framing | Partly | `audio_capture.c`, 16 kHz, 32-bit slots, 4 × 160-frame DMA | **Philips → MSB-justified**: measured one-bit misalignment on this board (DEC-06) | alignment sweep E-18 [VERIFIED] |
| 3 | Pin map BCK 4 / WS 5 / SD 6 | No | `sdkconfig.board`: BCK 6 / WS 5 / SD 4 | follows the existing wiring (C-05) | audio live E-02 [VERIFIED] |
| 4 | int16 = bits 23:8 (word >> 16) | Yes | `reader_task`: `(int16_t)(raw[i] >> 16)` | level concern (C-07) measured and closed (DEC-09) | E-06 [DOCUMENTED] |
| 5 | MONO slot mode may halve DMA traffic (EXP-10) | Tested, used | mono RX with the measured mic slot | — | 63 976 vs 127 963 B/s, E-05 [VERIFIED] |
| 6 | MIC_SETTLE ≥ 300 ms for power-up zeros | Kept | stereo probe discards 300 ms | no zero-blanking seen; a DC transient instead, settles in-band within 100 ms (DEC-10) | E-04, E-19 [DOCUMENTED] |
| 7 | microfrontend: 30 ms / 10 ms, 40 mel, **125–6 500 Hz**, noise reduction + PCAN, int8 | Yes | vendored TFLM microfrontend, all parameters from `model/frontend.json` | — | parity E-21 [VERIFIED] |
| 8 | 512-pt real FFT via esp-dsp, **float** | No | microfrontend's own fixed-point KissFFT | bit-exact parity with training needs the same FFT code on both sides (C-02) | CPU measured instead (E-23, E-56) [VERIFIED] |
| 9 | Single `frontend.json` + golden-vector parity test + hash check | Yes (manual, not CI) | `gen_frontend_config.py`, `psfe.py`, `parity_test.py`, SHA in firmware and model | a libm rounding difference required host tables on the device (DEC-16) | 12 000/12 000 bit-exact [VERIFIED] |
| 10 | 1-D DS-CNN, **stateful streaming**, inference every 30 ms | Partly | DS-CNN with "valid" convolutions, **windowed** (whole 1.02 s window) every **60 ms** | deadline risk of int8 streaming state in TFLM (DEC-11, user-approved) | CPU still < 10 % (E-56, E-60) [VERIFIED] |
| 11 | Shortlist of 3 model families compared on DET curves (EXP-8) | No | one family (DS-CNN) with six data/weighting variants | descoped for time (PROJECT_STATE §7) | — [VERIFIED] |
| 12 | Train from random init; no pre-trained keyword model | Yes | `train.py` builds layers from scratch; seed 26172; no weight loading | — | code review E-14 [VERIFIED] |
| 13 | TFLite Micro + esp-tflite-micro + esp-nn, pinned | Yes | `idf_component.yml` `==1.4.1`; `dependencies.lock` hashes | — | device output = host reference, 1 984/1 984 (E-22) [VERIFIED] |
| 14 | No ESP-SR anywhere; automated gate | Yes | `tools/forbidden_deps.py` runs on every build | — | "forbidden_deps: PASS" in build logs [VERIFIED] |
| 15 | End-of-keyword labels ± 160 ms with masking | Yes (variant) | positives = windows ending 0–160 ms after the keyword end; prefix windows negative; the rest masked | window is 0…+160 ms, not ± | lag and prefix behaviour, E-25 [DOCUMENTED] |
| 16 | Smoothing window 5, threshold 0.95 | Changed | mean of **3** scores, threshold **0.80** | chosen by a declared rule on validation data (selection_v2_outcome.json) | test sessions E-35, E-59 [VERIFIED] |
| 17 | 2 s refractory before any false-activation count | Yes | `kws_on_frame`: 2 000 ms | — | live = offline replay, E-26 [DOCUMENTED] |
| 18 | Unified ring, 1.0 s; pre-roll 624 ms | Yes, then trimmed | `audio_ring.c`; product ring **0.75 s**, pre-roll **571 ms** (the study's own "window 5" row) | memory (DEC-22), justified by measured lag ≤ 144 ms | min slack 169–179 ms, 0 overruns (E-53, E-63) [VERIFIED] |
| 19 | Three cursors on one ring | Simplified | one writer + one reader; pre-roll is "w − N"; the front end reads the fresh hop directly | a front-end cursor was unnecessary | — [VERIFIED] |
| 20 | Warm TCP from boot, 8-byte header, 20 ms frames, 2 frames/packet, OVERRUN marker | Yes | `netstream.c`; fixed payload sizes per packet type (the header has no length field) | keepalive 10 s instead of 15 s (the clock pings double as keepalive) | 24/24 and 30/30 clean streams (E-36, E-60) [VERIFIED] |
| 21 | ADPCM mode, throughput probe, degradation ladder | No | PCM16 only | descoped | — [PLANNED] |
| 22 | NTP-style clock-offset estimator over the same socket | Yes | PING/PONG/INFO; lowest RTT of the last 8 | — | ± 1.2–1.8 ms half-RTT in T1 [VERIFIED] |
| 23 | Self-hosted Vosk/Kaldi ASR, WebRTC-VAD endpointing | Yes / changed | Vosk `en-in-0.5`; **energy VAD** in the speech band | no extra package; ASR endpoint unusable on this audio (E-48) | E-49, E-61 [DOCUMENTED] |
| 24 | Latency L1/L2/L3 with GPIO + playback rig as ground truth | Partly | L1 and L2 from software timestamps; keyword end located in the streamed audio | no logic analyser or playback rig (C-06); a 10 ± 7 ms term is estimated | E-37, E-63 [VERIFIED] |
| 25 | CPU by GPIO duty cycle (primary) + cycle counters + run-time stats | Partly | GPIO16 toggled per hop; `@PERF` cycle counts; `@CPU` run-time stats | GPIO never captured (no analyser); run-time stats became primary | E-56, E-60 [VERIFIED] |
| 26 | "256 KiB Arena Discipline": report, bound, enforce | Report only | S4 reported from linker map + heap minimum | bounded heap and allocation-failure hook not built | — [PLANNED] |
| 27 | Disclose the Wi-Fi blob in an SBOM | Yes | `docs/SBOM.md`; 9 closed libraries listed from the link map | — | E-15 [VERIFIED] |
| 28 | ≥ 6–10 h held-out ambient audio for false-activation claims | Partly | 10 h overnight (5 h declared held-out) + 2.47 h active household | quiet and active figures reported separately | E-39, E-51 [VERIFIED] |
| 29 | ≥ 100 activations per latency distribution | No | n = 22 (E-37), n = 12 (T1) | time | — [VERIFIED] |

## How the measurements compare with the study's estimates

The implementation is, in effect, the experiment the study asked for. Comparing its estimates with what was measured is the most useful lesson in this chapter.

Table: Study estimates versus measurements on the final build {#tab-est-vs-meas}
| Quantity | Study estimate [EST] | Measured | Main reason for the difference |
|---|---|---|---|
| Peak RAM, S4 | ≈ 227 KiB (232 400 B) | 245.0 KiB (250 899 B), E-60 | the budget left out code placed in internal RAM (IRAM, 54 591 B) — conflict C-10 found at M0 |
| Model flash | 40–60 kB | 28 024 B | a smaller model than the study's reference class |
| Tensor arena | 32 KiB budget | 13 404 B used | same |
| Pipeline CPU (C1, one core) | ≈ 2.8 % | ≈ 9.25 % (i2s_reader task) | windowed model recomputes the whole 1 s window (≈ 3.9 %), and the fixed-point microfrontend with noise reduction costs ≈ 4.5 % |
| System CPU, both cores (C3) | ≈ 2.1 % | 5.53 % | as above, plus Wi-Fi with power save disabled |
| L1 detection → server | ≈ 13 ms | 2.4 ms (START) / 18 ms (first audio, with ASR load) | LAN and warm TCP as designed; the extra ≈ 16 ms is the server's receive scheduling while Vosk runs |
| L2 keyword end → server | ≈ 205 ms | 138 ms median | smoothing over 3 scores (≈ 120 ms span) instead of 5 |
| Mic pass-band edge | 6 768 Hz | visible in the recorded spectrum (E-03) | agrees |

:::key
The study was right about *where* the problems are (network stack and RTOS memory, false activations, parity) and wrong by about 3× about *how much CPU* the audio path takes — mostly because two of its assumptions (a float esp-dsp FFT and a streaming model) were not implemented. The measured numbers still pass, but with less margin than the study predicted.
:::

## What the implementation does *not* establish about the research

- It does **not** validate the study's model comparison: only one model family was trained, so nothing here shows that DS-CNN is better or worse than TC-ResNet or dilated convolutions.
- It does **not** test Architectures B or C, ADPCM, UDP or speculative streaming.
- It does **not** reproduce the microWakeWord numbers the study quotes (tensor-arena sizes, esp-nn issues); those remain [DOCUMENTED] claims about other projects.
- It **does** give real measurements for the study's own budget categories on the same chip and microphone, which is exactly what the study said it lacked ("there are currently zero [MEAS] values in this document").

## Which parts are the study's, and which are this project's

The **study** contributed the problem framing (false activations first), the datasheet analysis, the budgeting method (S0–S4, C1–C3, L1–L3), the compliance positions (no ESP-SR, disclose the Wi-Fi blob, train from scratch, non-transformer ASR), the pre-roll derivation, the warm-TCP transport and the parity rule.

The **implementation** contributed everything that required hardware: the measured I2S framing, the libm-table parity fix, the IRAM discovery and memory trims, the decision to run a windowed model, the device-identical replay evaluation, the hard-negative mining from the device's own mistakes, the server's ASR conditioning and threading, the measured latency decomposition, and all the evidence. Chapter 13 discusses which of these are genuinely distinctive.
