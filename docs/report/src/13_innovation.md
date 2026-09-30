# The Most Distinctive Engineering Contributions {#ch-innovation .chapter}

## How this chapter judges "innovation"

Using a neural network on a microcontroller, streaming audio over Wi-Fi or running an open-source recogniser is not innovative in itself — thousands of projects do each of these. This chapter looks for **specific engineering decisions in this build that solve a problem that the ordinary approach would handle badly**, and it holds each one to evidence. It makes no claim of global novelty or patentability: the related literature was not surveyed, and several ideas below were proposed by the architecture study and are credited to it.

Table: Ordinary choices, for contrast (necessary, well-established, not claimed as contributions) {#tab-ordinary}
| Choice | Why it is ordinary |
|---|---|
| TensorFlow Lite Micro + esp-nn on an ESP32-S3 | Espressif's standard path for int8 inference |
| DS-CNN keyword model, int8 post-training quantisation | a standard microcontroller keyword-spotting design since 2017 |
| The TFLM microfrontend (log-mel with noise reduction and PCAN) | TensorFlow's own "micro_speech" front end |
| Vosk (Kaldi) as the recogniser | a common self-hosted open-source ASR |
| TCP streaming of 16-bit PCM | the simplest reliable transport |

## Level A — Conceptual contributions

### A1. Making every requirement falsifiable before building

**The challenge.** The PS's limits ("< 256 KB RAM", "< 10 % CPU", "near-zero false activations", "latency from keyword end") are ambiguous enough that almost any system could be *described* as compliant.

**Why the ordinary approach falls short.** The usual practice is to report the most favourable number — model size instead of total RAM, one core's inference time instead of system CPU, detection-to-send time instead of keyword end to server, accuracy on a clean test set instead of false triggers per hour.

**The choice made.** Adopt the strictest defensible reading of each requirement *before* measuring, and measure it with instruments the reader can re-run: S4 includes IRAM code, every stack and the Wi-Fi buffers with PSRAM disabled, and is checked against both kB and KiB; CPU is reported per core *and* averaged; latency starts at the keyword's acoustic end; false triggers are reported per condition with exposure hours; selection rules and data splits are committed before the data they judge exists.

**Evidence of usefulness.** It changed outcomes: the strict memory reading exposed the IRAM omission and forced real engineering (260 → 245 KiB); the strict latency reading replaced a flattering 95 ms with the measured 138 ms; the declared rules made two departures from them visible and documented instead of silent (the v2 amendment and DEC-26). **What remains unproven:** that evaluators read the requirements the same way. **Credit:** the framing (nested scopes, three latency definitions, kill conditions) is the architecture study's; the execution and the evidence are this project's.

### A2. Privacy as a property of the data flow

The device transmits nothing but clock-sync packets until a detection, and the stream is bounded (571 ms before, the command, a hard 10 s cap). This is a design property that can be checked in code (`ns_trigger` is the only path that starts a stream). The project also states the honest corollary: a false trigger sends 2–6 s of room audio, so privacy is exactly as good as the false-trigger rate. [VERIFIED]

## Level B — Architectural contributions

### B1. A front end that is bit-identical on the chip and in training

!fig #fig-parity figures/parity.svg | How train/deploy parity is enforced: one definition, one set of C sources compiled twice, canonical start-up tables, and three hash checks. | 100

**The challenge.** A keyword model learns the exact statistics of its input features. If the device computes them even slightly differently from the training pipeline, accuracy degrades silently — the study lists this as failure modes X3 and X4.

**Why the ordinary approach falls short.** Typical pipelines compute training features with a Python library (librosa, TensorFlow ops) and device features with C code, and check them only by eye or with a tolerance. Even a shared library can differ across platforms, as this project found.

**The choice made and how it works.** (1) One JSON file defines every feature parameter; the firmware compiles it into a header, the training code reads it at run time, and both carry its SHA-256. (2) The *same* C source files — the vendored microfrontend and KissFFT — are compiled for the Xtensa core and for the PC (`libpsfe.so`, called from Python through ctypes). (3) Because the chip's maths library computes two start-up tables differently from the PC's, the PC's tables are exported and copied into the device at boot, again guarded by the JSON hash. (4) The model records the front-end hash its training data used, and the firmware refuses to run a model built for a different front end.

**Components.** `frontend.json`, `gen_frontend_config.py`, `psfe.py`, `build_twin.sh`, `export_tables.py`, `ps_frontend_diag.cc`, `parity_test.py`, `kws_init()`.

**Trade-offs.** It rules out the faster float esp-dsp FFT the study wanted (the FFT must be the same code on both sides), costing CPU; the canonical tables add 1 402 bytes of flash (288 + 288 + 125 16-bit values).

**Evidence.** 12 000/12 000 feature frames and 1 984/1 984 model outputs bit-exact; live device triggers identical to offline replay on three separate recordings (27/27, 39/39, 12/12). [VERIFIED] **Unproven:** parity was tested on room audio and speech at normal levels; extreme levels (clipping) were not specifically exercised.

**Why it matters.** It converts the device into something that can be *simulated exactly*. Every accuracy number in this report — including comparisons of models that were never flashed — rests on this.

### B2. One ring buffer, sized from measurement, that fails safe

**The challenge.** The device knows the keyword was said only after it ends, so it must keep recent audio; memory is scarce; the stream must never deliver corrupted audio if the network stalls.

**The choice made.** A single int16 ring written once per hop on core 1 and read by the streamer on core 0; positions are sample counts since boot, so the pre-roll start is `w − 9 136` and "was I overtaken?" is one subtraction; release/acquire atomics instead of a lock; an explicit OVERRUN message and a short stream when the reader is lapped. The ring was then *shrunk from 1.0 s to 0.75 s* using the study's own table, once the measured worst-case detection lag (144 ms) justified it.

**Trade-offs.** Only 179 ms of slack beyond the pre-roll — which is exactly why the server's blocking recogniser caused overruns (Problem 11).

**Evidence.** 0 overruns in 30/30 and 12/12 final streams; the 3 overruns during the server fault were all flagged, none delivered as corrupted audio; 23/23 streams bit-exact against the device's own audio. [VERIFIED] **Credit:** the unified-ring idea and the pre-roll derivation are the study's (§8.3–§8.5); the measured sizing, index arithmetic and the evidence are this project's.

### B3. Measuring "keyword end → server" without laboratory equipment

**The challenge.** The PS's latency starts at the moment the keyword *acoustically* ends — an event neither computer timestamps. The study's answer was a loudspeaker rig that raises a GPIO at a known sample, plus a logic analyser; neither was available.

**The choice made.** Split the path into three pieces and measure each where it is observable: (1) the device's detection time converted to server time by an NTP-style offset carried over the *same* warm TCP connection (±1.2–1.8 ms); (2) the server's receive time of the first audio packet; (3) the keyword's end located *inside the streamed audio itself* — possible precisely because the stream starts 571 ms before the detection — and measured back from the detection point. The one unobservable piece (last captured sample → decision, ≈ 10 ms) is stated as an estimate with an error bar rather than ignored.

**Evidence.** The method reproduced itself exactly when re-run (E-37 recomputed identically on 30 Sep) and gives the full per-activation breakdown in [[fig-latt1]]. **Unproven:** the 10 ± 7 ms term; energy-based keyword-end location fails when a command follows with no pause (one session was unusable, E-62). **Why it matters:** it produces an L2 figure whose every component is either measured or explicitly estimated.

### B4. Core partitioning that makes the CPU claim clean

All work that happens every 10 ms — capture, conversion, ring, features, inference, decision — runs in **one** task pinned to core 1 at priority 20; Wi-Fi, TCP, streaming and telemetry run on core 0. Besides protecting the audio path from Wi-Fi interrupt storms, this makes the "idle listening" CPU of the pipeline directly visible as core 1's busy time, and per-stage cycle counters inside that task attribute it. The study proposed this split (§4.8); the implementation simplified it from three tasks to one. [VERIFIED] **Trade-off:** core 1's margin (≈ 0.5 point) is thin because everything is concentrated there; **unproven:** whether moving the front end to core 0 would help overall.

## Level C — Implementation contributions

### C1. A closed-loop data engine built on the device's own mistakes

**The challenge.** A new keyword has no public dataset, the team had one speaker at first, and household sound caused false triggers that no synthetic data represented.

**Why the ordinary approach falls short.** Typical custom-wake-word pipelines mix clean clips into generic noise datasets; the model never sees this microphone, this room, or the specific sounds that fool it.

**The choice made and how it works.**

- **Everything is mixed into audio recorded through the product's own microphone** in the target room (beds), at randomised SNR and room gain.
- **Every example is a continuous stream with a 2.5 s lead-in**, so the front end's adaptive noise reduction and gain control are in the same state as on the always-on device when the keyword arrives.
- **Labels are placed by the keyword's end**, with "prefix" negatives that teach the model not to fire on "Hey Vy…".
- **The deployed model's own live scores** — logged for every inference during hours of real household audio — are used to find the moments it found keyword-like (score ≥ 0.30), and those moments become weighted negatives for the next model. Only declared *training* hours are mined; held-out hours stay untouched.

**Evidence — including where it did not work.** The live logs made v3 and v4 possible within hours. Mining quiet-night mistakes (v3) made household false triggers *worse* (19.9 vs 15.8 /h); mining household TV/talk mistakes (v4) made them *better* (9 vs 13 in the held-out hour) but hurt a new speaker's recall (14/25 vs 20/25). [VERIFIED] **Interpretation:** the loop works as a mechanism; its data must contain the right *kind* of negatives and more than one speaker's positives. **Unproven:** that the loop converges with more speakers — the obvious next experiment.

### C2. Fitting the strictest RAM reading through configuration engineering

**The challenge.** The strict S4 reading counts IRAM code and all Wi-Fi/TCP/IP buffers, which the architecture's budget had missed; the first product build was 4.3 KB over 262 144 B and 10.5 KB over 256 000 B.

**The choice made.** Attribute every byte (linker sections + heap reports after each initialisation step), then remove what the product does not need rather than shrinking the model: move Wi-Fi, FreeRTOS, ring-buffer and heap code from IRAM to flash; size the arena from `arena_used_bytes()`; size the ring from the measured lag; write the model input in place; trim Wi-Fi/lwIP buffers and disable features a 32 kB/s uplink does not use (A-MPDU, IPv6, heap poisoning).

**Evidence.** 266 483 → 243 767 (not streaming) → 259 255 (streaming, over) → 249 615 → final 250 899 B; every step measured and recomputed. [VERIFIED] **Trade-offs:** code from flash competes with model weights for cache, making inference time vary with Wi-Fi traffic [INFERRED]; ≈ 5 kB of margin remains. **Credit:** the "network stack and RTOS, not the model, dominate" insight is the study's; the IRAM finding (C-10) and the trims are this project's.

### C3. ASR conditioning referenced to the keyword

**The challenge.** Device speech arrives quiet and on top of fan rumble; a moving gain changed transcripts between near-identical takes; the recogniser's own end-of-utterance rule did not work on this audio.

**The choice made.** The pre-roll always contains the keyword, spoken by the same person at the same distance just before the command. The server uses it twice: to set **one fixed gain** for the whole stream (keyword speech → −20 dBFS, after a 150 Hz high-pass), and to set the **VAD threshold** relative to the keyword's level (keyword − 20 dB). Recognition runs in its own thread so it can never block reception.

**Evidence.** The controlled experiment (a LibriSpeech sentence: correct → "that" at device level → correct after conditioning, E-45); 30/30 clean streams after the thread change; demonstration 3/4 commands exact. **Unproven:** a systematic word-error-rate comparison with and without conditioning on real commands (only small sessions exist).

### C4. Compliance as code

A build cannot complete if any vendor wake-word SDK or known pre-trained wake-word model is referenced anywhere in the repository (`forbidden_deps.py`, run by the build wrapper); the closed Wi-Fi/PHY libraries were listed from the linker map, not from memory; "trained from scratch" is checkable in `train.py`; two non-commercial training voices are disclosed with the retraining path. The study recommended the gate (X25); the project automated it. [VERIFIED]

## How the contributions relate to the research

Table: Research proposal vs what the build added {#tab-innov-trace}
| Contribution | Proposed by the study | Added by this project |
|---|---|---|
| A1 falsifiable requirements | nested scopes, three latency definitions, kill conditions | the measurements; the IRAM correction; declared rules in files; documented departures |
| B1 parity | single JSON, golden-vector test, hash in model metadata | same-source host twin via ctypes; the libm table discovery and canonical tables; live = replay proofs |
| B2 ring buffer | unified ring, pre-roll derivation, OVERRUN | index arithmetic with atomics; resizing from measured lag; evidence under failure |
| B3 latency | L1/L2/L3; playback rig + GPIO | in-stream keyword-end location; explicit estimated term |
| B4 core split | pipeline on core 1, network on core 0 | one task; per-stage cycle attribution |
| C1 data engine | domain-matched negatives through the demo mic; end-of-keyword labels | streams with front-end warm-up; mining the deployed model's live scores; v3/v4 evidence |
| C2 memory | "follow the bytes"; PSRAM off; buffer trims | IRAM finding; measured attribution; product/capture build split |
| C3 ASR conditioning | self-hosted Vosk, server endpointing | keyword-referenced gain and VAD; ASR thread |
| C4 compliance | ESP-SR gate, SBOM disclosure | automation in the build; link-map evidence |
