# Complete Experimental and Validation History {#ch-experiments .chapter}

This chapter reconstructs, in time order, every test that shaped the final system — including the failures and the results that were later corrected. Each test is described in the same format. Dates and times come from commit times, run-folder names and the evidence ledger; results marked [VERIFIED] were re-computed from the raw files for this report, the rest are [DOCUMENTED] ledger entries whose raw files exist but were not re-analysed.

!fig #fig-phases figures/phases.svg | The development and validation timeline. Each box is a group of tests or a decision; the ledger IDs point to Appendix A. | 100

## Test categories used in this project

Table: Kinds of testing that were actually done {#tab-testkinds}
| Category | What it means here | Examples |
|---|---|---|
| Hardware validation | does the physical part behave as its datasheet says, on this board? | I2S alignment sweep, mono mode, start-up, pass band, levels |
| Integration (parity) | do two independent implementations of the same step agree bit for bit? | device vs host features, device vs host model outputs, live vs replayed triggers, server WAV vs device audio |
| Functional | does a subsystem do its job? | Wi-Fi/TCP bring-up, streaming with pre-roll, ASR endpointing |
| Performance | how much memory, CPU and time does it take? | EXP-1 memory, EXP-2 CPU, latency L1/L2 |
| Accuracy and reliability | how often does it detect, and how often does it fire wrongly? | scripted keyword sessions, new speaker, overnight and household exposure |
| End-to-end | keyword → stream → transcript on the real chain | M6 command sessions, T1 |
| Demonstration | a recorded run of the whole system | E-61 |

There were **no unit tests** in the software-engineering sense and no continuous-integration server; the architecture's CI gates (§B9) were implemented as scripts run by hand, except the forbidden-dependency gate, which runs automatically on every build.

## Summary of all tests

Table: Every significant test, in order {#tab-alltests}
| When | Test | Category | Key result | Outcome |
|---|---|---|---|---|
| 26 Sep 20:50 | M0 build + X25 gate | build | image 241 095 B, gate PASS | pass |
| 26 Sep 21:45 | I2S alignment sweep | hardware | Philips 1 bit late; MSB aligned | design changed (MSB) |
| 26 Sep 21:45 | EXP-10 mono slot | hardware | 63 976 vs 127 963 B/s | pass |
| 26–27 Sep | start-up / settle, levels, integrity | hardware | no zero blanking; DC transient; link faults found and fixed | settle kept at 300 ms |
| 27 Sep 13:42 | M2 feature parity | integration | 5 995/5 998 frames | **fail** → fixed |
| 27 Sep 14:57 | M2 parity after fix | integration | 12 000/12 000; 8/8 tables | pass |
| 27 Sep 14:57 | M3 model output parity | integration | 1 984/1 984 bit-exact | pass |
| 27 Sep 14:57 | M3 per-stage cycles | performance | front end 4.66 %, inference 3.11 % | informative |
| 27 Sep 15:11 | v0 live on S01 session 2 | accuracy | 20/25, 6/16 confusables; live = replay 27/27 | baseline |
| 27 Sep 18:46 | v2 selection | accuracy (validation) | declared rule → v2b@0.98 (12/25); amended → v2b@0.80 (17/25) | rule amended, documented |
| 27 Sep 19:27 | "live" v2b test | accuracy | first read as a failure; no keyword had been spoken | **corrected** |
| 27 Sep 19:32 | Wi-Fi on/off noise A/B | diagnostic | Wi-Fi hypothesis rejected | pass |
| 27 Sep 19:52 | S01 session 3 (held-out) | accuracy | **22/25**, 2/16 confusables | headline recall |
| 27 Sep 19:52 | streaming + integrity | functional / integration | 24/24 streams, 0 overruns; 23/23 bit-exact | pass |
| 27 Sep 19:52 | first latency | performance | L1 1.66 ms; L2 95 ms median | superseded by T1 |
| 27–28 Sep night | 10 h false-activation exposure | reliability | 29 FA / 10 h; 1 in the 5 h held-out block | informative |
| 28 Sep 07:53 | EXP-1 non-streaming | performance | 260.2 KiB → trims → 238.1 KiB | pass after DEC-22 |
| 28 Sep 08:01 | EXP-2 first CPU | performance | core 1 8.6–8.9 % | pass |
| 28 Sep 17:50 | first ASR session | end-to-end | empty transcripts — no command had been spoken | **corrected** |
| 28 Sep 19:27 | M6 command test, small ASR | end-to-end | edge works; ASR 1/4 | fail at ASR |
| 28 Sep 20:18 | M6 v2, en-in-0.5 + VAD | end-to-end | 6/10 detected, 2/10 exact end to end | partial |
| 28 Sep 22:18 | household FA, v2b vs v3 | reliability | v2b 15.8 /h, v3 19.9 /h | v3 rejected |
| 28 Sep 22:26 | EXP-1 streaming peak | performance | 259 255 B — fails 256 000 | **fail** → DEC-24 |
| 28 Sep 22:55 | EXP-1 after DEC-24 | performance | 249 615 B | pass |
| 28 Sep 23:01 | EXP-2 12 min | performance | core 1 max 9.04 % | pass |
| 28 Sep 23:05 | v4 selection rules a–c | accuracy | pass | pending (d) |
| 29 Sep 19:22 | v4 rule (d), fresh commands | accuracy | 10/10 both | v4 selected |
| 29 Sep 19:46 | final v4 firmware + ASR server | performance / functional | 3/31 overruns | **fail** → server fix |
| 29 Sep 20:12 | new speaker S02 | accuracy | v4 14/25, v2b 20/25 | v2b shipped (DEC-26) |
| 29 Sep 20:23 | final v2b confirmation | performance / functional | 245.0 KiB, 30/30 clean, idle 9.32 % | pass |
| 29 Sep 22:13 | demonstration run | demonstration | 4/4 keywords, 3/4 commands exact | recorded |
| 30 Sep 08:43 | latency re-analysis with ASR | performance | L1_audio0 7–11 ms; L2 81 ms (n = 9) | informative |
| 30 Sep 08:55 | T1 on the final configuration | performance / accuracy | 12/12; L2 138 / 196 ms | headline latency |

## Phase 0 — Toolchain (26 Sep)

### M0: pinned build and the compliance gate

- **Objective:** a reproducible firmware build from a pinned toolchain, with the ESP-SR gate in place before any code exists.
- **Setup and method:** ESP-IDF v5.5.5 installed natively (not PlatformIO, which pinned IDF 6.1 with GCC 15, DEC-01); `tools/idf.ps1 -Console uart build`.
- **Result:** green build, image 241 095 B, `forbidden_deps: PASS`; the M1 build's static internal RAM was 93 371 B, of which 60 015 B was **code placed in internal RAM (IRAM)** (E-01, E-17). [DOCUMENTED]
- **Interpretation and next step:** that IRAM line is not in the architecture's memory budget at all. It was logged immediately as conflict C-10 — "this could move the headroom to negative" — and it became the central problem of EXP-1 two days later.

## Phase 1 — Physical audio (26–27 Sep)

### I2S alignment sweep (E-18)

- **Objective:** confirm that the samples arriving at the chip are the microphone's samples, bit for bit.
- **Hypothesis:** Philips framing, as the study's compatibility table specified (P-02).
- **Method:** at every boot the firmware captures 0.3 s with each of four configurations (Philips / MSB-justified × normal / inverted bit clock) and reports, per slot, the fraction of samples whose 24-bit least significant bit is 1 (≈ 50 % for real audio; 0 % if the data arrives one bit late) and whether the empty slot stays empty.
- **Result:** Philips: LSB = 1 in 0.00 % of samples, and 3.3 % of the empty slot's words non-zero (sign bits leaking in). MSB-justified: LSB = 1 in 50.85 %, empty slot 100 % zero. Inverted clocks gave the same verdicts. Repeated on two boots. [VERIFIED — `runs/20260926_214456_m1_align_sweep_warm/device_log.txt`]
- **Status:** hypothesis rejected; **design changed** to MSB-justified framing (DEC-06). Root cause (sampling edge or WS timing) not isolated.
- **Why it matters:** with the wrong framing every sample is halved and loses its lowest bit — the audio still *sounds* right, so the error would have survived into training and deployment unnoticed.

### EXP-10: does mono mode halve DMA traffic? (E-05)

- **Method:** measure bytes per second delivered by DMA in stereo and in mono mode.
- **Result:** stereo 127 963–127 965 B/s; mono 63 976 B/s (4 boots, identical). [VERIFIED]
- **Status:** pass — mono is used, which also removes the empty slot from the capture path.

### Start-up blanking and settling (E-04, E-19)

- **Hypothesis:** the datasheet's 2^18-clock zero output after power-up (≈ 256 ms).
- **Result:** no zeros — the first non-zero word came 0.56 ms after the clock started, on 3 warm boots and 1 cold power-up. Instead, a DC offset of up to 26 % of full scale decays over ≈ 1.5 s; in the 125–6 500 Hz feature band the level is at the room floor after 100 ms. [DOCUMENTED]
- **Status:** the study's 300 ms settle time is enough for the features; a proposed 2–3 s settle (C-11) was withdrawn (DEC-10). The sample (one cold boot) is small.

### Levels and pass band (E-02, E-03, E-06)

- **Method:** scripted cold-boot session A: silence, speech at 0.5 m, a steady "shhh", speech at 1 m; spectra and 100 ms levels.
- **Result:** feature-band room floor −52.9 dBFS (fan on); words at −38…−42 dBFS peaks; the 6 768–8 000 Hz band 15.8 dB below 4 000–6 768 Hz. [DOCUMENTED; spectrum re-plotted in [[fig-psd]]]
- **Interpretation:** the level is low but usable; keeping the top 16 bits (`>> 16`) is fine (DEC-09); the mel ceiling at 6 500 Hz is justified by the measured roll-off.

### Capture-link integrity (E-07, E-20, E-40)

- **Objective:** make sure recordings used for training and testing have no hidden gaps.
- **Findings and fixes:** (1) a 100 ms USB write timeout lost frames → 1 s; (2) the Windows USB serial driver ignored a bare RTS pulse, so the board was not actually reset and a stalled link persisted → esptool's DTR/RTS sequence and a check that `@BOOT` arrives before audio is accepted; (3) a "USB connected?" check in the firmware briefly read false while the host was reading and dropped frames → removed; (4) a host-side stall watchdog that auto-resets into a new session. [DOCUMENTED]
- **Result after fixes:** 60 s clean, then the overnight run: 36 000 s, 0 CRC errors, 0 I2S overflows, 1 gap of 20 ms (320 samples), 0 auto-resets. [VERIFIED — `ambient_night_20260927/capture_summary.json`]

## Phase 2 — Front-end parity (27 Sep)

### M2 golden-vector parity: first attempt fails (E-21)

- **Objective:** prove the device computes exactly the features the model will be trained on (study §7.3; failure modes X3, X4).
- **Method:** the device streams its int16 audio *and* its 40-value feature frames over USB; the PC recomputes the features from the same audio with the host twin (same C sources); frames are compared value by value, and the front-end SHA-256 must match.
- **Result (60 s):** 5 995 of 5 998 frames identical; 3 values in 3 frames differed (bands 34–35, max difference 26). **FAIL.** [VERIFIED — `runs/20260927_134200_m2_parity_60s/parity_report.json`]
- **Investigation:** a per-table hash diagnostic (`@FETAB`) showed the **filterbank weights differ**: they are computed at start-up with `log1pf()`, and the chip's C library (newlib) rounds differently from the PC's (glibc). The PCAN lookup table's first comparison was inconclusive because the hash included never-initialised slots — the hash was fixed to cover only the entries the code reads.
- **Change:** the host twin's tables are exported to `ps_frontend_tables.c` and copied into the device's state after initialisation, if their recorded JSON hash matches (DEC-16).
- **Result after the fix:** 12 000/12 000 frames bit-exact over 120 s and 3 001/3 001 in a second run; 8/8 table hashes equal. **PASS.** [VERIFIED]

## Phase 3 — Model on the device (27 Sep)

### Deployment parity and footprint (E-22, E-24)

- **Method:** the device sends every raw int8 model output; the PC runs the same `.tflite` with TensorFlow Lite's reference kernels on the host-twin features of the same audio.
- **Result:** 1 984 of 1 984 outputs bit-exact (esp-nn on the device vs reference kernels on the PC). Model 28 024 B; arena used 13 404 B of 40 960 reserved; 10 665 parameters. [VERIFIED]
- **Meaning:** combined with feature parity, *any* recording can be evaluated on the PC with the certainty that the device would have produced the same scores.

### Per-stage CPU with cycle counters (E-23)

- **Result (capture build, v0):** front end 111 758 cycles per 10 ms hop = 4.66 % of core 1 (upper bound: includes queuing the USB frame); inference 448 178 cycles on average (756 202 max) × 16.7 per second = 3.11 %; 0.47 multiply-accumulates per cycle (the study assumed 0.5). [VERIFIED — `posterior_parity.json`]
- **Interpretation:** the pipeline would take ≈ 8 % of one core — three times the study's 2.8 % estimate, but inside 10 %. The windowed model (DEC-11) and the fixed-point microfrontend explain the difference.

### v0 — first model, first real speaker (E-25, E-26, E-27, E-28)

- **Setup:** v0 trained on synthetic speech only; S01 was completely excluded from training, so this is a speaker-independent test.
- **Results:** offline on S01 session 1: 22 of 23 located keywords at threshold 0.9 (N = 3); median detection 0.19 s after the keyword's end. Live on the device, S01 session 2: 20/25 keyword prompts, but **6 of 16 confusables fired** ("Hey", "Hero", "Hey bro", "Vayu", "Hey Vayu", "Pyro"). The device's 27 live triggers were **identical** to an offline replay (E-26). 0 false activations in 401 s of held-out daytime audio (too short to mean much: < 27 /h at 95 %). [VERIFIED — E-26; others DOCUMENTED]
- **Consequence:** the confusable failures drove the v2 synthetic data (faster speech, many "Hey + X" negatives). The live-equals-replay result made offline evaluation trustworthy.

### v1 and the validation lesson (DEC-18)

v1 scored better than v0 on synthetic validation (PR-AUC 0.949 vs 0.929) but worse on the real speaker (18/23 vs 22/23). Choosing models by synthetic validation would have picked the worse model; choosing by S01 would have been selecting on the test speaker. **Decision:** create a real-speech validation set separate from the test set — S01 session 2 for validation, later sessions for testing (DEC-19). [DOCUMENTED]

### v2 selection — a declared rule, and its amendment (E-30)

- **Declared rule (18:18, before results):** minimise false activations on the 16 confusable prompts of S01 session 2; then maximise recall; ties → the higher threshold. Candidates: v2a (balanced class weight) and v2b (positive weight 4), thresholds 0.80/0.90/0.95/0.98.
- **Outcome:** the rule selected **v2b @ 0.98 — 12/25 recall** (2/16 confusables).
- **Amendment (18:46, before any held-out test):** "highest recall subject to ≤ 3/16 confusables" → **v2b @ 0.80 — 17/25 recall, 3/16**. The recorded reason: the validation set is tiny (differences of 1–2 confusables are not significant), a pure false-activation-first rule collapsed recall to 48 %, and confusable prompts are only a proxy for what really matters (false activations per hour on held-out audio). Both outcomes are recorded in `selection_v2_outcome.json`. [VERIFIED]
- **Honest reading:** this is a post-hoc choice on validation data. Its protection is that every *test* afterwards (sessions recorded later, the night, the household, the new speaker) was untouched by it.

## Phase 4 — Streaming and the first real test (27 Sep evening)

### Network bring-up (E-32)

Wi-Fi station up, warm TCP connection about 1.5 s after boot; internal heap free with Wi-Fi up 64 456 B in the capture build. [DOCUMENTED]

### A "failed" live test that was not a test (E-33, E-34)

- **What happened:** a 150 s live session produced no detection, and the first interpretation was that the model failed in the noisier evening room.
- **Investigation:** a controlled A/B (30 s with Wi-Fi off, 30 s on, same minute) rejected a Wi-Fi interference hypothesis — Wi-Fi *on* was not louder in any band (E-34). The evening room *was* 10–15 dB louder at 5–8 kHz than the afternoon (insects/appliances, cause unconfirmed).
- **Correction:** the user then confirmed that the keyword had **not been spoken** in that session — the prompt was not seen in time. The session was reclassified as 150 s of non-keyword audio with 0 false activations. [DOCUMENTED]
- **Lesson recorded:** never interpret a result before confirming what was actually said. The same kind of correction happened again on 28 Sep (E-45).

### S01 session 3 — the held-out keyword test (E-35)

- **Setup:** recorded after v2b was frozen; protocol v2 (25 keyword prompts at 0.5/1/2 m including fast, slow and soft; 16 confusables; free talk); evening room; Wi-Fi and streaming on; v2b @ 0.80 live on the device.
- **Result:** **22/25 keyword prompts** (0.5 m normal 4/6, fast 2/3, slow 3/3; 1 m 6/6, soft 2/2; 2 m 5/5); **2/16 confusables** ("Hey Vayu", "Tyre"); median detection 80 ms after the energy-located keyword end. For information: v0 21/25 & 4/16, v2a 21/25 & 1/16. [VERIFIED — `model/artifacts/v2b/eval_test_S01_s3.json`]
- **Limit:** S01 also recorded the training session 1, so this is **speaker-dependent**; confusable prompts are adversarial, not a false-activation rate.

### Streaming integrity (E-36, E-44)

- **Result:** 24/24 detections streamed with pre-roll, each ended by the server, 0 overruns, 0 sequence gaps, minimum ring slack 376 ms (1.0 s ring, 624 ms pre-roll); the keyword's end lay inside the pre-roll in 22/24. Each server WAV was located inside the device's own USB recording and compared sample by sample: **23/23 bit-exact** (the 24th came after the USB capture ended). [VERIFIED — `server/20260927_192112/stream_integrity.json`]
- **Side finding:** the files of 10 earlier, unattended activations had been overwritten because the device restarts activation numbers at each reboot; server files are now named by connection time (E-38 remains unresolved: whether those 10 detections were real is unknown).

### First latency measurement (E-37)

- **Method** (used again in every later latency test): the device sends its detection time; the server timestamps the START message and the first audio packet on its own clock; the ping-based offset converts one into the other (uncertainty = half the round-trip time). To get from the *keyword's end* rather than the detection, `latency_report.py` finds the keyword's acoustic end inside the streamed audio itself (speech-band energy, 20 ms resolution) — possible because the stream starts 624/571 ms before the detection — and measures how long before the detection point it lies. The remaining piece, from the last sample in the ring to the detection decision, cannot be seen in the audio; it is taken as **10 ± 7 ms (estimated)**.
- **Result:** detection → START 1.66 ms median (p95 2.18); → first audio 2.12 ms; keyword end → detection 84 ms median (max 144); **L2 ≈ 95 ms median, 136 ms p95** (n = 22). [VERIFIED — `server/20260927_192112/latency_report.json`, re-run 30 Sep with identical numbers]
- **Conditions:** capture build, a server without ASR, LAN, one session. Later superseded as the headline by T1.

## Phase 5 — The overnight run (27–28 Sep)

### False activations by household activity (E-39, E-40, E-41)

- **Setup:** v2b @ 0.80 live on the device for 10 h (20:31–06:31) with Wi-Fi and streaming on; the user confirmed the keyword was never spoken. **Before recording**, the split was declared in `sources.json`: hours 1–5 (c000–c004) for training v3, hours 6–10 (c005–c009) held out.
- **Result:** 29 false triggers in 10 h, but very unevenly spread: 27 in the first two hours while the household was awake (≈ 13.5 /h), 2 in the 8 h asleep; **1 in the 5 h held-out block (0.2 /h; 95 % upper bound ≈ 0.95 /h)**. [VERIFIED — [[fig-night]], from `posteriors_device.bin`]
- **Network outage (E-41):** the router dropped at 00:44 and came back at 06:08 on a *different subnet*; the device kept detecting and logging throughout, retried TCP every ~20 s, but could not reach the server because its address is compiled in.
- **Interpretation:** "false activations per hour" depends overwhelmingly on whether people are talking. The quiet-night number must never be quoted alone (the ledger's own rule).

!fig #fig-night figures/night_fa.svg | False triggers per hour in the overnight run (v2b live on the device). The declared held-out block is the last five hours. Generated from `posteriors_device.bin`. | 85

## Phase 6 — Product configuration (28 Sep morning)

### EXP-1: peak memory, first product build (E-42)

- **Objective:** the study's kill-condition experiment — does the whole system fit in 256 KB with PSRAM off?
- **First measurement:** the first product build measured **S4 = 266 483 B (260.2 KiB) — over both limits**. [DOCUMENTED]
- **Changes (DEC-22):** USB capture streams off (the 64-slot transmit pool alone was ~30 KB of `.bss`); tensor arena 40 → 16 KiB (13.4 KiB used); ring 1.0 → 0.75 s and pre-roll 624 → 571 ms, using the study's own table row for 5-score smoothing because the measured worst-case detection lag was 144 ms (E-37); Wi-Fi buffers trimmed (static RX 4, dynamic RX 16, TX 16 at this point); lwIP send/window buffers 4 096; Wi-Fi, FreeRTOS, ring-buffer and heap functions moved out of IRAM into flash; model input written in place (no separate window buffer); reader stack 3 584.
- **Result:** static 139 123 B + peak heap 104 644 B = **243 767 B (238.1 KiB)**, *not streaming* (the PC and the board were on different subnets after the outage, so no stream could be opened). [VERIFIED — recomputed]

### EXP-2: first idle CPU (E-43)

Three 10 s windows on the product build, Wi-Fi associated (TCP not connected): core 1 busy 8.63–8.92 %, core 0 0.74–1.08 %, both cores ≈ 4.8–5.0 %; cycle counters: front end 4.36 %, inference 3.46 % of core 1. [VERIFIED] Short, but the first product-configuration CPU number.

### v3 declared and trained (DEC-23)

v3 = v2 recipe + night beds + hard negatives mined from the *training* night hours; its threshold rule selected 0.60 (20/25 on validation). Ship rule declared first: ship v3 only if it has fewer false activations than v2b on a *new* active-household recording **and** S01 session-3 recall ≥ 21/25.

## Phase 7 — Speech recognition (28 Sep afternoon and evening)

### First ASR session, and a second correction (E-45, E-46, E-47)

- **Observation:** with the small Vosk model, live streams produced empty or wrong transcripts, and the first detection → first audio time was ≈ 190 ms.
- **Correction:** the user confirmed that **no command had been spoken** after the keyword in that session; one stream held only devotional singing from another room — a genuine false activation (E-47). The empty transcripts were therefore not evidence of ASR failure.
- **Controlled finding that stood:** a clean LibriSpeech sentence decodes correctly; the same sentence scaled to the device's measured speech level (−40 dBFS) with this room's background decodes to "that"; after an 8th-order 150 Hz high-pass and gain it decodes correctly again. → `AsrFrontEnd`.
- **The 190 ms** was a server artefact: the recogniser was being created inside the receive thread at START; the device had sent the first audio 2.8 ms after the detection. Fixed by pre-creating it (E-46). [DOCUMENTED]

### M6 live command test with the small model (E-48)

- **Setup:** S01, 5 scripted "Hey Vayro … <command>" prompts at 30–50 cm; capture build; Vosk small en-in-0.4, open vocabulary.
- **Result:** edge side worked — 6 triggers, 4 streamed and all 4 bit-exact; L1_start 2.2–2.5 ms, first audio 13.9–17.7 ms; one keyword missed (single-score spike 0.78, average 0.61). **ASR: 1 of 4 correct** ("open the door"). The small model heard the commands as noise, so Vosk ended utterances only on its 5 s silence rule; the long streams then blocked the next keywords (one stream at a time). Offline replay reproduced the live transcripts exactly. [DOCUMENTED]
- **Status:** **failing at the ASR stage.** Changes: an energy VAD on the server with a rule fixed before evaluation (`VadEndpointer`), a fixed keyword-referenced gain, and the larger `en-in-0.5` model (user-approved download).

### M6 live validation v2 (E-49, E-50)

- **Setup:** 10 new keyword + command prompts (said once each), en-in-0.5 + VAD endpointing; capture build v2b @ 0.80; TV on; household active.
- **Result:** keyword detected in 6/10 prompts (5 streamed; 1 detected but a stream from the user's early repetition was still open); streams: 0 gaps, 0 overruns, L1_audio0 4.9–10.1 ms, VAD END 1.6–2.2 s after the trigger. ASR exact on 2 of the 5 prompted streams ("stop the music", "open the door"); errors "turn off the light" for *turn on*, "sir joseph" for *switch on the fan*; word error rate 7/18 ≈ 39 %. **End to end: 2/10.** The user listened to two streams: the commands were clearly intelligible, so the errors are the recogniser's, not audio damage. [DOCUMENTED]
- **Capture stalls (E-50):** four USB link stalls happened while the PC was unzipping and loading the 1 GB model (≈ 1 GB free RAM); ≈ 4 minutes affected. Rule adopted: no heavy host work during long captures.

### Household false activations: v2b vs v3 (E-51)

- **Setup:** 2.47 h of evening household audio (TV, family talk, prayer), nobody addressing the device; the M6 test minutes excluded. Both models replayed on the same audio with the device-identical pipeline.
- **Result:** **v2b 39 false triggers = 15.8 /h; v3 49 = 19.9 /h.** v2b's 39 offline detections equal the device's 39 live triggers. On the M6 v2 prompts inside the recording (not part of the rule), v3 detected 9/10 vs v2b 6/10. [VERIFIED — `household_compare_20260928.json`]
- **Decision:** v3's ship rule failed on false activations → **v2b stays** (DEC-23). Analysis of v2b's misses: 3 of the 4 missed prompts had a single high score (0.78/0.74/0.86) but a low average — the keyword was said with no pause before the command.

## Phase 8 — Memory under streaming, and v4 (28 Sep night)

### EXP-1 while streaming (E-52 → DEC-24 → E-53)

- **Method:** product configuration, v2b, TCP connected, 31 synthetic triggers (`T` byte) every 10 s, each streaming the 571 ms pre-roll plus 3 s of live audio; static RAM from the size report, peak heap from the lowest free heap during the run.
- **First result:** 141 047 + 118 208 = **259 255 B** — passes 262 144 by 2 889 B, **fails 256 000 by 3 255 B**. Streaming costs ≈ 17 KB of heap at its peak. [VERIFIED — recomputed]
- **Changes (DEC-24, configuration only):** heap poisoning off (a debugging aid), Wi-Fi A-MPDU aggregation off in both directions (a 32 kB/s uplink does not need it, and each block-ack session holds buffers), at most 8 queued Wi-Fi TX buffers, IPv6 off.
- **Result:** 139 695 + 109 920 = **249 615 B** — passes both limits (+6 385 B vs 256 000); 31/31 streams, 0 overruns, minimum slack 169 ms. [VERIFIED — recomputed]

### v4 built and selected on its declared rule (E-54, E-55)

- **Declared first** (`selection_rule_v4.json`, commit 3ffc188, amendment before the build): v4 = v3 + keyword-then-speech positives + household training-part negatives and beds. Ship v4 only if (a) fewer false activations than v2b on the held-out household hour, (b) S01 session-3 recall ≥ 21/25, (c) ≤ 2 false activations in the 5 h held-out night, (d) at least as many hits as v2b on a fresh command session recorded after v4 is frozen.
- **Results:** threshold from validation 0.70 (no threshold reached 20/25; best 17/25). (a) held-out household 0.86 h: **v4 9 vs v2b 13** (10.4 vs 15.1 /h) ✓; (b) 21/25 ✓; (c) 0 vs 1 in 5 h ✓. Reported but not in the rule: M6 v2 prompts v4 8/10 vs v2b 6/10. [VERIFIED — `selection_v4_outcome.json`]

### EXP-2 for 12 minutes (E-56)

- **Setup:** trimmed product build, v2b, idle listening, Wi-Fi + TCP connected, 72 windows of 10 s, no triggers.
- **Result:** core 1 busy **mean 8.81 %, max 9.04 %**; i2s_reader task 8.78 %; core 0 0.82 %; both cores **4.82 %** mean (max 5.16 %). Cycle counters: front end 4.46 %, inference 3.59 % of core 1. [VERIFIED — recomputed]
- **Status:** pass. Not done: the GPIO/logic-analyser cross-check (no analyser); interrupt time is under-counted by the method.

## Phase 9 — The final decisions (29 Sep)

### v4 rule (d): a fresh command session (E-57)

S01 said 10 new commands once each, after v4 was frozen; both models replayed on the USB recording: **v2b 10/10, v4 10/10**, no detections outside the prompts. Rule (d) passed, so by its declared rules **v4 @ 0.70 was selected** and its firmware built. The server could not be reached during this session (the PC's network had not recovered from sleep), so streaming was not measured. [VERIFIED — `prompt_hits_20260929_192230_m6_v3_S01.json`]

### Final v4 firmware: overruns with the ASR server (E-58)

- **Result:** RAM 251 495 B and idle CPU (both cores 4.72 %) passed. But with the ASR server in the loop, **3 of 31 streams overran and 1 timed out** — the same configuration had 31/31 clean with the plain server (E-53).
- **Diagnosis:** Vosk decoding ran inside the server's receive loop; it sometimes stalled for up to ≈ 0.6 s; the server stopped reading the socket; TCP flow control backed up into the device; the streamer fell behind; the 0.75 s ring has only ≈ 180 ms of slack beyond the 571 ms pre-roll, so it overflowed. The overruns were correctly flagged — no corrupted audio was delivered.
- **Fix:** `AsrJob` — recognition moved to its own thread per stream; the receive loop only timestamps, runs the cheap VAD and queues audio. Offline replay regression identical. [DOCUMENTED; fix VERIFIED in E-60]

### The new speaker (E-59) and the override (DEC-26)

- **Setup:** a second person, S02, recorded the standard keyword session (25 prompts, 16 confusables) on the capture build running v4; neither model had heard S02; no tuning.
- **Result:** **v4 @ 0.70: 14/25** (0.5 m 10/12, 1 m 3/8, soft 0/2, 2 m 1/5), 0/16 confusables. **v2b @ 0.80: 20/25** (0.5 m 10/12, 1 m 6/8, 2 m 4/5), 1/16. Across all real keyword tests after v4 was built: v2b 58/70, v4 53/70. [VERIFIED — `eval_newspk_S02_s1.json` for both models]
- **Decision (DEC-26, team, 20:20):** **ship v2b @ 0.80**, overriding v4's declared rule, which had no new-speaker criterion because no second speaker existed when it was written. Accepted cost: more household false triggers (13 vs 9 in the held-out hour). The override is recorded as such in `selection_final.json`.

!fig #fig-acc figures/accuracy_compare.svg | The evidence behind DEC-26: keyword detection on four real test sets (left) and false triggers on two held-out exposures (right), v2b vs v4. Generated from the evaluation JSON files. | 100

### Final firmware confirmation (E-60)

- **Setup:** product build with v2b @ 0.80 (ELF `6294c691f`), threaded ASR server; 190 s idle, then 30 synthetic streams.
- **Result:** device identity `run=v2b sha f7c913efdbb28f64 thr 80 arena_used 13404`; **RAM 139 695 + 111 204 = 250 899 B (245.0 KiB)**; **30/30 streams ended by the server, 0 overruns**, minimum slack 169 ms (the server fix works live); **idle CPU core 1 mean 9.32 % (max 9.51 %), core 0 1.74 %, both cores 5.53 %**. [VERIFIED — recomputed; [[fig-cpu]]]
- **Observation made for this report:** during the 30-stream phase core 1 averaged **10.51 % (max 10.83 %)**. The reader task rose from 9.25 % to 9.95 % because inference cycles went up (555 k → 603 k per inference) while the Wi-Fi task was busy — consistent with model weights and Wi-Fi code competing for the flash cache after the IRAM trims [INFERRED]. The 10 % limit applies to idle listening, so this is not a violation, but it had not been reported before.

!fig #fig-cpu figures/cpu_final.svg | CPU per 10 s window in the final confirmation run: idle listening, then one synthetic stream every 10 s. Generated from `device_events.jsonl` (FreeRTOS run-time statistics). | 90

### Demonstration run (E-61)

A real-time recording of the real system: capture build (v2b + USB audio for the recording) for the keyword-and-command part, product firmware for the idle part. 4/4 prompted keywords detected (+1 repeat); the server heard "turn on the light", "what time is it", "open the door" exactly and "openly to / place your music" for *play some music* — **3 of 4 commands exact**; 0 triggers while the speaker talked without the keyword; every stream 0 lost packets; first audio 6.5–57 ms after detection; product-firmware idle core 1 8.77 / 8.79 %. The capture build's own CPU lines read 10.6–11.4 % (USB audio + streaming). [DOCUMENTED]

## Phase 10 — Latency on the final configuration (30 Sep)

### Latency with the ASR server in the loop (E-62)

Re-analysis of three 29 Sep sessions after fixing a file-name bug in `latency_report.py` (it had silently skipped every session recorded after the server began naming files `c<time>_act<n>`; E-37 was re-computed identically as a check). Detection → first audio: median 6.7, 7.1 and 10.6 ms in the three sessions (p95 15–42, max 57 ms), versus 2.1 ms without ASR load. Keyword end → server in the draft demo session: 81 ms median, 172 ms p95 (n = 9). The final demo take's L2 was unusable (the command followed the keyword with no pause, so the energy locator found the end of the *command*). [DOCUMENTED]

### T1 — latency and detection on exactly the shipped configuration (E-63)

- **Objective:** replace the 27 Sep latency (different build, no ASR) with a measurement on the final product firmware and the final threaded server.
- **Setup:** `host/t1_session.py` starts the server (Vosk en-in-0.5, VAD endpointing) and the device console hidden, waits for the board to connect, then prompts 12 times "Say: Hey Vayro (then stay quiet)", 6 s apart; S01 at ~40 cm.
- **Result:** **12/12 prompts detected, 0 extra triggers**, 0 lost packets, 0 overruns, all streams ended by the server (minimum slack 179 ms). Detection → START 2.4 ms median; **detection → first audio 18.0 ms median, p95 29.8, max 36.6**; keyword end → detection 111 ms median (p95 171); **L2 = 138 ms median, 196 ms p95, 198 ms max**. Clock uncertainty ±1.2–1.8 ms. The server's transcripts contained only keyword-like words ("cairo", "pyro", …) and nothing after the keyword, as expected; the transcript was ready 43–339 ms (median 135 ms) after the device's END. [VERIFIED — `server/20260930_085548/latency_report.json` and activation JSONs; [[fig-latt1]]]
- **Why it differs from E-37:** the on-device decision lag was 27 ms longer in this session (keyword-end location varies between sessions and speakers; the 60 ms inference cadence quantises it) and the server's receive path added ≈ 16 ms while Vosk was loaded.
- **Limits:** n = 12, one speaker, one quiet session; the capture term is estimated; the study's target of ≥ 100 activations was not reached.

!fig #fig-latt1 figures/latency_t1.svg | T1, per activation: the three parts of the keyword-end → server latency. Generated from `latency_report.json`. | 95

## What cannot be reconstructed reliably

- **E-38:** ten detections on the evening of 27 Sep while no capture was running; their audio was overwritten, and whether anyone said the keyword is unknown.
- **Physical conditions:** speaker distances are nominal (as prompted), room noise levels were not calibrated in SPL, and the TV volume during household recordings was not recorded.
- **Two demo "silent" takes** were discarded because someone spoke to the board; they are not evidence of anything.
- **The capture term** of the latency (≈ 10 ms) was never measured.
