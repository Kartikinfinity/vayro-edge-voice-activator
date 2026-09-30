# Technical Glossary and Study Notes {#ch-glossary .chapter}

## Glossary

Each entry gives a plain definition and, where useful, what the term means *in this project*.

### Hardware and electronics

Table: Hardware terms {#tab-g-hw}
| Term | Meaning | In this project |
|---|---|---|
| SoC (system-on-chip) | processor, memory and peripherals on one chip | the ESP32-S3 |
| Xtensa LX7 | the processor core design used in the ESP32-S3 | two cores at 240 MHz |
| SRAM / internal RAM | fast on-chip working memory, lost at power-off | 512 KB on the chip; the 256 KB budget is measured here |
| PSRAM | external pseudo-static RAM, larger and slower | 8 MB present in the package, **disabled** so it cannot hide memory use |
| Flash | non-volatile storage for code and constants | 16 MB on the chip, 4 MB configured; holds the firmware and the model weights |
| IRAM | part of internal RAM that holds executable code for speed | 54 591 B of code; counted in the RAM budget |
| Cache | small fast memory that keeps recently used flash contents | 32 KB instruction + 64 KB data; model weights and flash code compete for it |
| DMA / GDMA | hardware that moves data between a peripheral and memory without the CPU | carries I2S audio into 4 × 10 ms buffers |
| GPIO | general-purpose input/output pin | GPIO4/5/6 for the microphone; GPIO15/16 for instrumentation |
| MEMS microphone | a microphone made with micro-machined silicon | INMP441 |
| I2S | a 3-wire serial bus for digital audio (bit clock, word select, data) | microphone → I2S0 at 1.024 MHz |
| Philips vs MSB-justified framing | two I2S timings; Philips starts the data one bit after the word-select edge, MSB-justified on it | MSB-justified was measured to be the correct one here |
| Slot | one channel's time share in an I2S frame | the mic uses the left 32-bit slot |
| USB-Serial-JTAG | the S3's built-in USB port that appears as a serial port and a debugger | COM7: power, flashing, telemetry, evidence |
| Group delay | the fixed time a signal takes to pass through a filter | 1.078 ms inside the microphone |
| dBFS | decibels relative to digital full scale (0 dBFS = the largest representable level) | room floor −53 dBFS, speech peaks −38…−42 dBFS |

### Embedded software

Table: Embedded software terms {#tab-g-emb}
| Term | Meaning | In this project |
|---|---|---|
| ESP-IDF | Espressif's official open-source development framework | v5.5.5 |
| FreeRTOS | a small real-time operating system with tasks, queues and priorities | tasks pinned to cores; run-time statistics give CPU use |
| Task / priority / pinning | an independent thread of execution; which runs first; fixing it to one core | `i2s_reader` on core 1 at priority 20 |
| Stack high-water mark | the least free stack a task has ever had | used to shrink the reader stack to 3 584 B |
| Heap | memory allocated at run time | 289 708 B internal heap; lowest free 178 504 B |
| `.bss` / `.data` / `.text` | zero-initialised globals / initialised globals / code | the parts of static memory the linker reports |
| sdkconfig / Kconfig | ESP-IDF's configuration system | layered defaults files; project options `PS_*` |
| Partition table | how the flash is divided | "single app large": a 1.5 MB application slot |
| Atomic (release/acquire) | memory operations that are safely visible across cores in a defined order | the ring's write index |
| Watchdog | a timer that resets a stuck system | IDF defaults; not tuned |
| NVS | ESP-IDF's key-value store in flash | used by Wi-Fi; erased once because of the old Arduino layout |

### Signal processing and features

Table: Signal-processing terms {#tab-g-dsp}
| Term | Meaning | In this project |
|---|---|---|
| Sample rate | samples per second | 16 000 Hz |
| Hop / window | how far the analysis moves each step / how much audio each step looks at | 10 ms / 30 ms |
| Hann window | a taper applied before the FFT to reduce edge effects | on 480 samples |
| FFT | fast algorithm for a signal's frequency content | 512-point, 16-bit fixed point (KissFFT) |
| Mel scale / filterbank | a frequency scale matching human pitch perception / filters that group FFT bins into bands on it | 40 bands, 125–6 500 Hz |
| Log-mel features | logarithm of the mel band energies | the model's input, 40 per 10 ms |
| Noise reduction (spectral) | subtracting a slowly tracked estimate of steady background per band | microfrontend, smoothing 0.025/0.06 |
| PCAN | per-channel energy normalisation — automatic gain control per band | strength 0.95 |
| High-pass filter | removes frequencies below a cut-off | 150 Hz 8th-order on the server, against fan rumble |
| VAD | voice-activity detection: is someone speaking? | server energy VAD in 300–4 000 Hz ends each stream |
| SNR | signal-to-noise ratio | training mixes at 0–25 dB |
| Pass band | the frequency range a filter lets through | the microphone's ends at 6 768 Hz at 16 kHz |

### Machine learning

Table: Machine-learning terms {#tab-g-ml}
| Term | Meaning | In this project |
|---|---|---|
| KWS | keyword spotting: detecting one phrase in continuous audio | "Hey Vayro" |
| ASR | automatic speech recognition: audio → words | Vosk on the server |
| CNN / depthwise-separable convolution | convolutional network / a cheaper convolution split into per-channel and channel-mixing steps | the DS-CNN model |
| Parameters / MACs | learned numbers / multiply-accumulate operations per inference | 10 665 / 212 584 |
| BatchNorm, ReLU, dropout, sigmoid | normalisation layer, activation, training-time regulariser, output squashed to 0–1 | used in `build_model()` |
| Receptive field / context | how much input one output depends on | 100 frames = 1.02 s |
| Quantisation (int8, PTQ) | storing weights and activations as 8-bit integers, calibrated after training | full-int8 model, 28 024 B |
| Scale / zero point | the two numbers that map int8 values back to real values | input 0.007567 / 4; output 1/256 / −128 |
| Tensor arena | the working memory TFLite Micro uses for intermediate tensors | 13 404 B used |
| TFLite Micro (TFLM) | TensorFlow's interpreter for microcontrollers | via esp-tflite-micro 1.4.1 |
| esp-nn | Espressif's optimised int8 kernels | selected automatically |
| Streaming vs windowed inference | computing only new steps with saved state vs recomputing a whole window | windowed (DEC-11) |
| Posterior / score | the model's probability output | *p*; averaged over 3 |
| Threshold, smoothing, refractory | decision level, averaging of scores, dead time after a trigger | 0.80, mean of 3, 2 s |
| TTS | text-to-speech synthesis | Piper, 4 voices |
| Hard-negative mining | adding the non-keyword examples the model currently gets most wrong | from the device's own live scores |
| SpecAugment | masking random frequency bands and time spans during training | 0–3 bands, 0–7 frames |
| Class weighting | weighting the rare class more in the loss | positive weight 4 in v2b |
| PR-AUC | area under the precision-recall curve | early stopping only |
| Train / validation / test split | data to learn from / to choose models and thresholds / to report results | declared in files before use |
| Speaker-disjoint | no speaker appears in more than one split | TTS by speaker ID; S02 never trained on |

### Testing and validation

Table: Testing terms {#tab-g-test}
| Term | Meaning | In this project |
|---|---|---|
| Parity (bit-exact) | two implementations give identical numbers | device vs host features and model outputs |
| Golden vector | a fixed input used to compare implementations | recorded device audio |
| Replay | re-running recorded audio through the same pipeline offline | `eval_stream.py`, `replay_session.py` |
| Recall / true-positive rate | fraction of keywords detected | 22/25, 20/25 |
| False activation (false trigger) | a detection with no keyword | 0.2 /h quiet, 15.8 /h TV |
| FA/h and exposure | false activations per hour, and the hours observed | always reported together |
| Rule of three | with 0 events in *T* hours, the 95 % upper bound is ≈ 3/*T* per hour | used for short clean exposures |
| Confusables | words deliberately similar to the keyword | 16 per session |
| Held-out | data never used for training or selection | night c005–c009, S01-s3, S02 |
| Declared rule | a selection criterion written before seeing the results | `selection_rule_v*.json` |
| p95 | the value below which 95 % of measurements fall | latency, CPU |

### Architecture, networking and measurement

Table: Architecture and networking terms {#tab-g-arch}
| Term | Meaning | In this project |
|---|---|---|
| Edge / cloud split | small always-on work on the device, heavy work on a server | KWS on the ESP32-S3, ASR on a PC |
| Pre-roll | audio from before the trigger that is sent with the stream | 571 ms |
| Ring buffer | a fixed-size buffer written in a circle | 0.75 s of int16 audio |
| Overrun | the writer overtakes the reader, destroying unsent data | detected and flagged; 0 in final runs |
| Warm connection | a connection opened in advance so no setup delay occurs at trigger time | TCP opened at boot |
| TCP_NODELAY | disables delaying small packets to combine them | set on both sides |
| Endpointing | deciding when an utterance has ended | server VAD |
| Clock offset (NTP-style) | estimating the difference between two clocks from timestamped round trips | ±1.2–1.8 ms |
| L1 / L2 / L3 | detection → server / keyword end → server / keyword end → server holds live audio | L1 18 ms, L2 138 ms, L3 not measured |
| S0–S4 | nested memory scopes from "model only" to "whole device" | S4 = 250 899 B |
| C1–C3 | CPU scopes: pipeline on one core / all app tasks / everything on both cores | core 1 9.32 %, both 5.53 % |
| SBOM | software bill of materials: every component, version and licence | `docs/SBOM.md` |
| Blob | closed, pre-compiled binary library | Espressif Wi-Fi/PHY libraries |

## How to understand this project in 15 minutes

1. **The job (2 min).** Detect "Hey Vayro" on a microcontroller, then send what follows to a speech recogniser — within 256 KB RAM and 10 % idle CPU, with open-source tools and a self-trained model. Read the Executive Summary table.
2. **The data path (4 min).** Look at [[fig-arch]] and [[fig-hop]]: 160 samples every 10 ms → int16 → ring → 40 log-mel features → every 60 ms the last 100 frames → DS-CNN → average of 3 ≥ 0.80 → stream from 571 ms earlier. Everything on core 1 in one task; networking on core 0.
3. **Why you can trust the numbers (3 min).** The device's features and model outputs are bit-identical to the PC's ([[fig-parity]]); therefore offline replay equals the device, and models can be evaluated on hours of real recordings.
4. **The results (3 min).** [[tab-final]]: 245.0 KiB, 9.32 %/5.53 % CPU, 138 ms L2, 22/25 and 20/25 recall, 0.2 and 15.8 false triggers per hour.
5. **What went wrong and how it was fixed (3 min).** One-bit I2S misalignment; maths-library rounding; IRAM code over the RAM budget; ASR blocking the network; v4 better on false triggers but worse on a new speaker → v2b shipped. The main open problem is TV/conversation false triggers.

## What to study deeply

These are the concepts an evaluator is most likely to probe, in order of importance for explaining this build:

1. **Keyword spotting as a detection problem** — why recall *and* false triggers per hour matter more than "accuracy"; exposure hours; the rule of three; why the quiet and TV numbers must be quoted together.
2. **Log-mel features and the microfrontend** — window, FFT, mel filterbank, noise reduction, PCAN, log; why the filterbank stops at 6 500 Hz.
3. **Depthwise-separable CNNs and int8 quantisation** — parameters vs MACs; scale and zero point; why BatchNorm disappears at export; why 66 % of the compute is in the first layer.
4. **Train/deploy parity** — why "the same C code" was not enough (maths-library rounding) and how the canonical tables and hashes fix it.
5. **Memory on the ESP32-S3** — static sections, IRAM, heap, stacks, cache; how S4 is computed; why the Wi-Fi stack costs more than the model.
6. **FreeRTOS scheduling and CPU measurement** — tasks, priorities, core pinning, run-time statistics and their blind spot (interrupts).
7. **I2S** — bit clock, word select, slot, framing; how the alignment sweep detects a one-bit shift.
8. **The streaming protocol and pre-roll** — ring indices, overrun, warm TCP, clock-offset estimation, how L2 is decomposed.
9. **Data engineering for a new keyword** — TTS spelling, mixing into device-recorded beds, end-of-keyword labels, speaker-disjoint splits, hard-negative mining from live scores, declared selection rules.
10. **The trade-offs that were chosen consciously** — windowed vs streaming model; smaller ring vs slack; Wi-Fi power save off; v2b over v4.
