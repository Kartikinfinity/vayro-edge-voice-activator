# Debugging, Failures and Engineering Iterations {#ch-debugging .chapter}

Chapter 10 told the story in time order. This chapter takes the most important technical problems one at a time and answers the same eight questions for each: what was observed, under what conditions, the suspected cause, how it was investigated, what evidence confirmed or rejected the cause, what was changed, what happened after, and whether it is resolved. Where the root cause was never proven, it says so.

## Problem 1 — Audio captured one bit late

1. **Observed:** with the planned Philips I2S framing, the lowest bit of every 24-bit sample was always 0, and the supposedly empty right slot contained small non-zero values.
2. **Conditions:** every boot, warm or cold; both bit-clock polarities.
3. **Suspected cause:** the receiver samples the data one bit-clock later than the microphone presents it — a framing mismatch between the INMP441 and the S3's Philips mode on this board.
4. **Investigation:** a built-in sweep over four framings, measuring two signatures that do not depend on what sound is present: the LSB-is-1 fraction (≈ 50 % for real audio) and the empty-slot contents (must be all zero).
5. **Evidence:** Philips 0.00 % LSB, 3.3 % non-zero words in the empty slot; MSB-justified 50.85 %, 0 %. Repeated on two boots. [VERIFIED]
6. **Change:** MSB-justified framing, locked in `sdkconfig.board` (DEC-06); runs recorded with Philips framing are excluded from training (`sources.json`).
7. **After:** every later recording shows correct statistics.
8. **Status:** **resolved in behaviour; root cause unconfirmed** — whether it is the S3's sampling edge, the WS timing or the breakout was not isolated (no logic analyser).

## Problem 2 — The evidence link lost data

1. **Observed:** single audio frames missing; once the board was never reset and a stalled link persisted; later, bursts of lost audio during long captures.
2. **Conditions:** Windows host; native USB; heavy PC load.
3. **Suspected causes:** timeouts too short for Windows USB scheduling; the Windows USB serial driver not forwarding a lone RTS change; a firmware "is USB connected?" check reading false while the host was actually reading; host CPU starvation.
4. **Investigation:** sample-index gap detection in `capture.py` (every audio frame carries its first sample index), CRC checks, device-side drop counters (`pool_drops`, `link_drops`), and correlating stalls with host activity.
5. **Evidence:** each fix removed its symptom; the overnight run then had 0 CRC errors and a single 20 ms gap in 10 h; later stalls coincided exactly with unzipping and loading the 1 GB ASR model (E-50). [VERIFIED / DOCUMENTED]
6. **Changes:** 1 s write timeout; esptool's DTR/RTS reset sequence plus waiting for `@BOOT`; removed the connection gate; 1 MB host receive buffer and high process priority; a stall watchdog that resets and starts a new, separately reported session; missing samples written as zeros *and* reported, never hidden.
7. **After:** clean multi-hour recordings.
8. **Status:** **resolved**, with an operating rule: no heavy PC work during long captures.

## Problem 3 — Device features did not exactly match training features

1. **Observed:** 3 values in 3 of 5 998 frames differed between the device and the host twin (bands 34–35, up to 26 units).
2. **Conditions:** same audio, same C sources, same `frontend.json`.
3. **Suspected cause:** the only thing not shared is the platform's maths library: tables computed at start-up with floating-point functions (`log1pf` for the filterbank, `powf` for PCAN, `cos`/`sin` for the window and FFT) might round differently on the chip (newlib) and the PC (glibc).
4. **Investigation:** hash every start-up table on both sides and compare (`@FETAB`, `compare_tables.py`); fix a hash that included uninitialised lookup-table slots (it had made the PCAN comparison meaningless).
5. **Evidence:** the filterbank weights differed; the other tables matched once hashed correctly. [DOCUMENTED — DEC-16; final 8/8 equality VERIFIED]
6. **Change:** export the host's tables (`export_tables.py` → `ps_frontend_tables.c`) and overwrite the device's copies after initialisation, guarded by the front-end JSON hash (DEC-16). The host's tables are the "canonical" ones because the training features were computed with them.
7. **After:** 12 000/12 000 and 3 001/3 001 frames bit-exact; model outputs 1 984/1 984 bit-exact.
8. **Status:** **resolved**. A three-in-six-thousand difference sounds harmless, but it would have made every later "device equals replay" comparison approximate instead of exact.

## Problem 4 — The model's first int8 export contained unsupported-looking operators

1. **Observed:** the converted model contained SHAPE, STRIDED_SLICE and PACK operators besides the expected ones.
2. **Cause (confirmed by the fix):** Keras 3 keeps a dynamic batch dimension through `Reshape`/`Flatten`, and the converter lowers that to shape arithmetic at run time.
3. **Change:** `export.py` rebuilds the network with `batch_size=1`, copies the trained weights and converts that static graph (DEC-17); the Keras `Flatten` was replaced by a `Reshape` with a static size.
4. **After:** only CONV_2D, DEPTHWISE_CONV_2D, RESHAPE, FULLY_CONNECTED, LOGISTIC; identical outputs on S01; the firmware registers exactly these five kernels. [VERIFIED]
5. **Status:** **resolved.** A related detail: TensorFlow's CPU depthwise kernel requires equal strides, so the code writes strides `(s, s)`; with a kernel width of 1 and input width 1 this is identical to `(s, 1)` (comment in `train.py`).

## Problem 5 — The synthetic voices said the wrong word

1. **Observed:** Piper's English voices pronounced "Hey Vayro" as "Hey VAY-ro" instead of "Hey VAI-ro".
2. **Investigation:** print each voice's phonemes for candidate spellings (`tts_probe.py`) and write sample WAVs for listening.
3. **Evidence:** "Hey Vayro" → /veɪɹoʊ/ in all three English voices; "Hey Vyro" → /vaɪɹoʊ/; Hindi "हे वाइरो" → /ʋaːɪɾoː/. [DOCUMENTED — DEC-14]
4. **Change:** the synthesiser is given "Hey Vyro" / "हे वाइरो"; the keyword itself is unchanged.
5. **Status:** **resolved by phonemes**; the planned human listening check was not recorded as done. [UNVERIFIED]

## Problem 6 — Validation on synthetic data picked the worse model

1. **Observed:** v1 beat v0 on the synthetic validation set (PR-AUC 0.949 vs 0.929) but detected fewer real keywords (18/23 vs 22/23).
2. **Cause:** synthetic speech is a different distribution from a real person through this microphone in this room (failure mode X16 in the study).
3. **Change:** a separate *real* validation session (S01 session 2) for all selection, a *different* real session for testing, and selection rules declared in files before results exist (DEC-18, DEC-19).
4. **Status:** **resolved as a method.** It is also the root of the v2 rule amendment and the DEC-26 override (Problem 11): with very little real data, every selection decision is fragile.

## Problem 7 — Labelling real keywords automatically was unreliable

1. **Observed:** the first energy-based labeller produced impossible keyword spans (0.02 s, 2.7 s) under fan noise; in session 2, speakers drifted to the end of their 2.5 s prompt windows and into the next prompt, so detections were credited to the wrong prompt (labeller recall 15/25 vs prompt recall 20/25).
2. **Changes:** labeller v2 (speech band 300–4 000 Hz, a threshold relative to each window's own floor, gap bridging, a 2 s cap); recording protocol v2 with 4 s windows and a "next:" preview (DEC-20); a label-free **prompt score** as the primary metric.
3. **Status:** **mitigated.** Keyword ends located by energy still have 20 ms resolution and can latch onto a command spoken with no pause (which made one latency session unusable, E-62).

## Problem 8 — Results misread before checking what was said

Two separate times, a result was first read as a failure and later corrected once the user confirmed what had actually been spoken: the 27 Sep "no detection in the evening" session (no keyword had been said, E-33), and the 28 Sep "ASR returns nothing" session (no command had been said; one stream held singing from another room, E-45, E-47). In between, a Wi-Fi-interference hypothesis for the evening noise was tested with a controlled on/off A/B and rejected (E-34). **Change:** ground truth is confirmed with the person before a result is interpreted, and both ledger entries were rewritten as explicit corrections that state the original, wrong interpretation. **Status:** **resolved as practice.** [DOCUMENTED]

## Problem 9 — The first product build did not fit in 256 KB

1. **Observed:** S4 = 266 483 B (260.2 KiB) — over both readings of the limit.
2. **Conditions:** the first "product" configuration with Wi-Fi, TCP, the model and the ring.
3. **Suspected cause (identified two days earlier as C-10):** the architecture's budget omitted **code placed in internal RAM** — ESP-IDF puts interrupt handlers, parts of FreeRTOS, the heap allocator and, by default, performance-critical Wi-Fi paths in IRAM, and under the strict reading that RAM counts. The capture-mode extras (a 64-slot USB transmit pool, a 40 KiB arena, a 1.0 s ring) added more.
4. **Investigation:** the linker's section sizes (`idf.py size`), per-step heap reports (`@MEM` after each initialisation step), and the stack high-water marks.
5. **Evidence:** IRAM `.text` was 60 015 B in the M1 build and 92 575 B in the first network build; the heap steps attributed 12 040 B to the front end and 53 060 B to Wi-Fi/lwIP/network tasks (E-17, E-29, E-42). [DOCUMENTED]
6. **Changes (DEC-22):** move Wi-Fi, FreeRTOS, ring-buffer and heap functions from IRAM to flash; capture streams off; arena sized to need (16 KiB); ring and pre-roll shortened using the study's own table (justified by the measured 144 ms worst-case lag); Wi-Fi/lwIP buffer trims; model input written in place; reader stack trimmed after measuring its high-water mark.
7. **After:** 243 767 B not streaming (E-42), then 259 255 B *while* streaming (E-52) — still 3 255 B over 256 000 — then DEC-24 (heap poisoning off, no A-MPDU, 8 TX buffers, no IPv6) → 249 615 B (E-53), final 250 899 B (E-60). [VERIFIED]
8. **Status:** **resolved with ≈ 5 kB of margin on the strict reading.** Trade-off: code executed from flash competes with model weights for the cache, which is the most likely reason inference gets slower when Wi-Fi is busy [INFERRED] (Chapter 12).

## Problem 10 — The speech recogniser heard nothing useful

1. **Observed:** empty or nonsense transcripts; Vosk ended utterances only at its 5 s silence limit; long streams hid the next keyword; transcripts flipped between near-identical takes; the first stream after start-up had an extra ≈ 25–40 ms delay.
2. **Conditions:** device speech around −40 dBFS at 30–50 cm with desk-fan rumble around −30 dBFS; the small `en-in-0.4` model; open vocabulary.
3. **Suspected causes:** level and low-frequency noise far from what the recogniser was trained on; a gain control that moved inside words; a weak model; the recogniser's own endpointing unsuitable; lazy library imports.
4. **Investigation:** a controlled experiment (`make_asr_control.py`, `asr_level_test.py`): one LibriSpeech sentence clean, then at the device's level with this room's recorded background, then with high-pass filtering and gain; and `replay_session.py`, which feeds recorded sessions through the real server code so variants can be compared on identical audio.
5. **Evidence:** clean → correct; device level + background → "that"; + 150 Hz 8th-order high-pass + gain → correct (E-45). Replay reproduced the live transcripts exactly and showed that gain rule, ASR start offset and recogniser persistence each flipped individual results — the small model was fragile (E-48). [DOCUMENTED]
6. **Changes:** `AsrFrontEnd` (high-pass + one fixed gain per stream, referenced to the keyword in the pre-roll); the larger `en-in-0.5` model; `VadEndpointer` with its rule fixed before evaluation; the recogniser pre-created and numpy/scipy imported at model load.
7. **After:** end to end 2/10 in a noisy live test with the TV on (E-49), 3/4 exact in the demonstration (E-61). The user's listening check showed the delivered audio was intelligible, so the remaining errors are the recogniser's.
8. **Status:** **partially resolved.** Delivery of audio is solid; recognition accuracy is limited by an off-the-shelf model (publisher's WER 36 %).

## Problem 11 — The ASR server caused stream overruns

1. **Observed:** 3 of 31 streams overran and 1 timed out with the ASR server; 0 of 31 with the plain server on the same firmware.
2. **Suspected cause:** the recogniser ran inside the server's receive loop; while it decoded, the server stopped reading the socket; TCP flow control pushed back to the device; the streamer could not send; the ring filled.
3. **Investigation:** replay timing of Vosk calls (stalls up to ≈ 0.6 s), and the device's own minimum-slack figure per stream (the 0.75 s ring leaves ≈ 180 ms beyond the 571 ms pre-roll).
4. **Evidence:** the arithmetic fits (a 0.6 s stall exceeds 180 ms of slack); the fix removed the symptom. [DOCUMENTED cause; fix VERIFIED]
5. **Change:** `AsrJob` — one recognition thread per stream fed by a queue; the receive thread only timestamps, runs the VAD and queues.
6. **After:** 30/30 streams clean with the ASR server (E-60); 12/12 in T1. [VERIFIED]
7. **Status:** **resolved.** The episode showed that the device's OVERRUN design works: the damaged streams were flagged and ended short, never delivered as corrupted audio.

## Problem 12 — False triggers in an active household

1. **Observed:** ≈ 13.5 false triggers per hour while the family was awake (E-39), 15.8 /h over 2.47 h of TV and conversation (E-51), one from devotional singing (E-47) — against 0.2 /h at night.
2. **Suspected causes:** the training data contained no television speech and almost no real household sound; short keyword-like fragments in continuous speech ("hey", "hero", "pyro"-like sounds).
3. **Attempt 1 (v3):** add the night's training hours as background and hard negatives. **Result:** worse — 19.9 /h (E-51). The night's hard negatives were quiet-room sounds, not speech. [VERIFIED]
4. **Attempt 2 (v4):** add household TV/talk negatives (hard-mined from v2b's own live mistakes) and keyword-then-speech positives. **Result:** better on held-out household audio (9 vs 13 false triggers in 0.86 h) and on commands, but a new speaker's recall fell from 20/25 to 14/25, collapsing at 1–2 m. [VERIFIED]
5. **Decision:** v2b ships (DEC-26); the accepted cost is the higher household rate.
6. **Interpretation:** with one training speaker, adding many hard negatives probably taught v4 a narrower idea of "Hey Vayro" [INFERRED]; the planned fix is more speakers *and* household data together (Chapter 15).
7. **Status:** **open — the main accuracy limitation of the system.**

## Smaller problems

Table: Other problems found and fixed (or not) {#tab-smallbugs}
| Problem | Cause | Fix | Status |
|---|---|---|---|
| Firmware would not build from `D:\sih final` | ESP-IDF does not support spaces in project paths | repository at `D:\ps26172` (DEC-02) | resolved |
| IDF environment script failed | the PC's default Python 3.14 | wrapper puts Python 3.12 first | resolved |
| PlatformIO would pin IDF 6.1 / GCC 15 | platform package choice | native ESP-IDF 5.5.5 (DEC-01) | resolved |
| Changed wiring/policy files silently ignored | ESP-IDF keeps an existing `sdkconfig` | wrapper deletes it when any defaults file is newer | resolved |
| esp-tflite-micro has no microfrontend | the component's source directory is absent | vendored from tflite-micro `aab6e2fd` (C-03) | resolved |
| NVS initialisation failed on first network boot | layout left by the pre-existing Arduino image | erase NVS once on a version/space error | resolved |
| A telemetry line lost its tail | text frames limited to 240 characters | `@STATS` split into `@STATS` + `@PERF` | resolved |
| Server files overwritten after device reboots | activation numbers restart at 1 on every boot | file names carry the connection time | resolved (10 activations lost, E-38) |
| Ctrl+C could not stop the server on Windows | `accept()` blocking | 1 s accept timeout loop | resolved |
| Latency report skipped every new session | file-name glob written for the old naming | glob fixed; E-37 reproduced as a check (E-62) | resolved |
| Server unreachable after the router restarted | server address compiled into the firmware | none | **open** (E-41) |
| Streams failed when the PC slept | the server process died | operating checklist: PC awake | **open** (procedural) |
| Boot waits 30 s without a USB host | `link_wait_host(30000)` kept from the evidence build | none | **open** |
