# Performance, Resource Usage and Final Results {#ch-results .chapter}

Every metric in this chapter is given with its definition, how it was measured, the conditions, the result, the target if one exists, and its limits. Where several measurements exist, the progression is shown and the final validated value is identified. Numbers are [VERIFIED] (re-computed from raw files) unless marked.

## Memory (RAM)

**Definition.** S4 = static internal RAM occupied by the application (from the linker: `.bss` + code in IRAM + `.data` + interrupt vectors) + peak heap use (heap total − the lowest free-heap value seen during a run that includes streaming). PSRAM disabled. The 96 KB of internal SRAM configured as CPU cache is excluded as hardware-reserved — a stated interpretation; counting it would add 98 304 B and break any application on this chip.

**Method.** `idf.py size` on the exact build + `@MEM`/`@STATS` heap minima from the device during 30–31 synthetic streams.

!fig #fig-mem figures/memory_progress.svg | Peak internal RAM (S4) at each EXP-1 measurement, recomputed from the size logs and the device's heap minima. The dashed line is 256 000 B, the dotted line 262 144 B. | 92

Table: Memory progression {#tab-memprog}
| Measurement | Static | Peak heap | S4 | vs 256 000 B | vs 262 144 B |
|---|---:|---:|---:|---:|---:|
| First product build (E-42 note) | — | — | 266 483 | −10 483 | −4 339 |
| E-42 after DEC-22, not streaming | 139 123 | 104 644 | 243 767 | +12 233 | +18 377 |
| E-52 streaming | 141 047 | 118 208 | 259 255 | **−3 255** | +2 889 |
| E-53 after DEC-24 | 139 695 | 109 920 | 249 615 | +6 385 | +12 529 |
| E-58 final v4 | 139 695 | 111 800 | 251 495 | +4 505 | +10 649 |
| **E-60 final v2b** | **139 695** | **111 204** | **250 899** | **+5 101** | **+11 245** |

**Target:** < 256 KB (PS). **Result:** met on both readings. **Interpretation:** the model and its arena are a small part (arena 16 KiB static; weights in flash); the Wi-Fi driver, lwIP, task stacks and IRAM code dominate — exactly as the architecture study predicted, although its total was ≈ 18 KiB too low because IRAM code was missing from its budget. **Limits:** one run per configuration; the heap peak depends on network conditions (streaming TX buffers), so a busier network could raise it; the scopes S0–S3 were not separately measured.

## Flash and model footprint

Table: Footprint {#tab-footprint}
| Item | Value | Source |
|---|---|---|
| Model (int8 `.tflite`, in flash) | 28 024 B | `metrics.json`, `@KWS` |
| Parameters / MACs per inference | 10 665 / 212 584 | `metrics.json` |
| Tensor arena reserved / used | 16 384 / 13 404 B | `@KWS` |
| Feature window buffer | 4 000 B (100 × 40 int8) | code |
| Firmware image | 901 059 B (of a 1 536 000 B partition; 41 % free) | size log |
| Flash code / read-only data | 669 272 / 157 212 B | size log |

No flash target exists in the PS; these are reported values.

## CPU utilisation

**Definitions.** *Core busy* = 100 % − idle-task share, from FreeRTOS run-time statistics every 10 s. *Busiest core* = core 1 (the audio pipeline). *Both cores (C3)* = their mean. *Idle listening* = no keyword, Wi-Fi associated, TCP connected. Cycle counters around the front end and `Invoke()` give per-stage attribution.

Table: CPU results {#tab-cpu}
| Run | Build | Windows | Core 1 busy mean / max | Core 0 mean | Both cores mean | Source |
|---|---|---:|---|---:|---:|---|
| E-43 | product (v2b) | 3 | 8.79 / 8.92 % | 0.93 % | ≈ 4.9 % | first check |
| E-56 | product, DEC-24 | 72 (12 min) | 8.81 / 9.04 % | 0.82 % | 4.82 % | longest run |
| E-58 | product, v4 | 18 | 8.67 / 8.79 % | 0.76 % | 4.72 % | [DOCUMENTED] |
| **E-60** | **product, v2b (final)** | **18** | **9.32 / 9.51 %** | **1.74 %** | **5.53 %** | final |
| E-60 streaming phase | same, 1 stream / 10 s | 31 | 10.51 / 10.83 % | 5.18 % | 7.85 % | not idle |
| capture build (demo) | USB audio on | 822 | ≈ 10.9 % | — | — | 28 Sep household run [DOCUMENTED] |

Per stage on core 1 (E-60 idle): front end ≈ 108 000 cycles per 10 ms hop = **4.5 %**; inference ≈ 555 000 cycles × 16.7/s = **3.9 %**; the rest of the reader task (conversion, ring, level meter) ≈ 0.9 %; total reader 9.25 %.

**Target:** < 10 % idle (PS). **Result:** met on both readings; the margin is about 0.5 point on the busiest core, 4.5 points on the average. **Interpretation:** the same code measured 8.6–9.5 % on core 1 across runs; inference cycles rise with Wi-Fi activity (492 k → 553 k per inference while the Wi-Fi task went from 0.48 % to 1.31 %), which fits model weights and Wi-Fi code sharing the flash cache after the IRAM trims [INFERRED — not isolated experimentally]. **Limits:** the GPIO duty-cycle method (the study's primary instrument) was not run; interrupt time is charged to the interrupted task, so idle-time interrupts are slightly under-counted; the streaming state exceeds 10 % on core 1.

## Latency

**Definitions.** *L1_start* = detection → START message read by the server. *L1_audio0* = detection → first audio packet read by the server. *Lag* = keyword's acoustic end → detection, measured in the streamed audio (20 ms resolution). *L2* = keyword end → first audio at the server = lag + capture term (10 ± 7 ms, estimated) + L1_audio0. *L3* (keyword end → server holding audio up to real time) was not computed.

!fig #fig-lat figures/latency_chain.svg | How the 138 ms median keyword-end → server latency (T1) is made up. | 100

Table: Latency measurements (ms) {#tab-latency}
| Session | Build / server | n | L1_start median | L1_audio0 median / p95 | Lag median | L2 median / p95 / max |
|---|---|---:|---:|---|---:|---|
| E-37, 27 Sep | capture / no ASR | 24 (L2: 22) | 1.66 | 2.12 / 4.27 | 84 | 95.4 / 136.3 / 163.7 |
| E-62, 29 Sep draft demo | capture / ASR | 9 | 1.85 | 6.74 / 15.3 | 64 | 81.3 / 171.8 / 179.3 |
| E-62, 29 Sep final confirmation | product / ASR, synthetic triggers | 39 | 1.80 | 10.6 / 22.0 | n/a | n/a (no keyword) |
| **E-63 T1, 30 Sep** | **product / ASR (final)** | **12** | **2.38** | **18.0 / 29.8** | **111** | **138.4 / 195.6 / 198.0** |

**Target:** none in the PS. **Final value:** **138 ms median, 196 ms p95** (T1). **Interpretation:** about 80 % of the time is the device's deliberate decision time (the keyword must be inside the 1 s window and three consecutive scores must average ≥ 0.80); the network and server add 2–20 ms. Detection → first audio grew from 2 ms to 18 ms when Vosk was running in the server process — server-side scheduling, not the device or the network (the device's own `@STREAM` lines show the first audio leaving 2–3 ms after detection). The architecture study estimated 205 ms for L2; the lower measured value comes from averaging 3 scores rather than 5. **Limits:** n = 12 (the study asked for ≥ 100), one speaker, a quiet home LAN; the 10 ms capture term is an estimate; keyword-end location is energy-based.

## Detection accuracy

Table: Keyword detection on real speech (v2b @ 0.80 unless noted) {#tab-recall}
| Test set | Speaker | Status of the data | Conditions | Result |
|---|---|---|---|---|
| S01 session 3 | S01 (also in training) | held-out session | 0.5 / 1 / 2 m, normal, fast, slow, soft; evening; live | **22/25**; 2/16 confusables |
| S02 session 1 | S02 (never trained on) | new speaker | same protocol | **20/25** (0.5 m 10/12, 1 m 6/8, 2 m 4/5); 1/16 |
| M6 v3 commands | S01 | fresh, after v4 froze | keyword + command, quiet | 10/10 |
| M6 v2 commands | S01 | fresh | keyword + command, TV on | 6/10 |
| T1 | S01 | fresh | keyword only, 40 cm | 12/12 |
| Demonstration | S01 | fresh | keyword + command | 4/4 |
| S01 session 2 | S01 | **validation** (used for selection) | protocol v2 | 17/25; 3/16 — not a test result |

**Interpretation.** On all real keyword prompts recorded after v4 was built (S01-s3, S02, M6 v2, M6 v3), v2b detected **58 of 70 (83 %)**. The misses are spread over normal, fast and slow speech at 0.5–1 m rather than concentrated at 2 m; a keyword spoken with no pause before a command is a known weak case (E-51). **Limits:** two real speakers, one room; the per-condition cells contain 2–12 prompts each, so differences of one or two are not meaningful; "confusables" are 16 deliberately similar words said once each, not a rate.

## False activations

Table: False triggers per exposure (v2b @ 0.80) {#tab-fa}
| Exposure | Hours | False triggers | Rate | 95 % upper bound | Source |
|---|---:|---:|---:|---:|---|
| Night, declared held-out block (asleep) | 5.0 | 1 | 0.2 /h | ≈ 0.95 /h | E-39 |
| Night, whole run (2 h awake + 8 h asleep) | 10.0 | 29 | 2.9 /h | — | E-39 |
| Evening household, TV + talk + prayer | 2.47 | 39 | **15.8 /h** | — | E-51 |
| Household held-out hour (rule a) | 0.86 | 13 | 15.1 /h | — | E-55 (v4: 9, 10.4 /h) |
| Daytime room, held-out chunk | 0.11 | 0 | 0 | < 27 /h | E-31 |
| 12-minute idle CPU run (quiet) | 0.20 | 0 | 0 | < 15 /h | E-56 |

**Target:** "near-zero" (PS, no number). **Result:** near zero when nobody is talking; about 16 per hour with television and conversation. **Interpretation:** the false triggers come from speech-like sound, not from noise. The exposures are strongly condition-dependent, so no single "FA/h" describes the system; the two numbers must always be quoted together. **Limits:** one household; about 13 h of exposure in total; TV volume and content not controlled.

## Streaming reliability and integrity

Table: Stream delivery {#tab-streams}
| Run | Streams | Ended normally | Overruns | Sequence gaps | Bit-exact vs device audio |
|---|---:|---:|---:|---:|---|
| E-36/E-44 (first test) | 24 | 24 | 0 | 0 | 23/23 checked |
| E-53 (synthetic, plain server) | 31 | 31 | 0 | 0 | — |
| E-58 (synthetic, ASR in receive loop) | 31 | 27 | **3** (+1 timeout) | 0 | — |
| **E-60 (final, threaded ASR)** | **30** | **30** | **0** | **0** | — |
| E-63 T1 | 12 | 12 | 0 | 0 | — |

The minimum ring slack is a direct health indicator: 376 ms with the 1.0 s ring (E-36), 169–179 ms with the 0.75 s product ring. **Result:** reliable on a home LAN once the server's receive path was freed. **Limit:** not tested on a congested network, which the study flagged as the main risk for L3.

## Speech-recognition quality

Table: ASR results (the recogniser is off-the-shelf; these describe it, not the edge system) {#tab-asr}
| Test | Model | Result |
|---|---|---|
| Publisher's benchmark | Vosk en-in-0.5 | WER 36.12 % (NPTEL) [DOCUMENTED — SBOM] |
| M6 command test, 28 Sep | small en-in-0.4, Vosk endpointing | 1/4 correct (E-48) |
| M6 v2, 28 Sep (TV on) | en-in-0.5 + VAD | 2/5 streamed commands exact; WER 7/18 ≈ 39 %; end to end 2/10 (E-49) |
| Demonstration, 29 Sep | en-in-0.5 + VAD | 3/4 commands exact (E-61) |
| T1, 30 Sep (keyword only) | en-in-0.5 + VAD | nothing reported after the keyword in 12/12 (correct); transcript ready 135 ms median after the stream ended |

## Stability

- **10 hours continuous** listening with Wi-Fi and streaming enabled: no crash, no auto-reset, 0 I2S overflows; it kept detecting through a 5.4 h router outage (E-39–E-41).
- **12 minutes** of idle CPU measurement without a single stray trigger (E-56).
- No long-duration test of the *product* build beyond 12 minutes exists. [VERIFIED]

## Data overhead

Nothing but 72 bytes of clock-sync data every 10 s is sent while idle. During a stream: 32 000 B/s of audio in 1 288-byte application packets (0.6 % header overhead), about 3.7 % including TCP/IP headers [INFERRED — calculated, not captured]. A keyword with no command costs about 67 kB; with a typical command about 110 kB.

## Power

Not measured. [UNVERIFIED]

## Final results at a glance

Table: The final, validated numbers and where each comes from {#tab-final}
| Metric | Final value | Evidence | Label |
|---|---|---|---|
| Peak RAM (S4) | 250 899 B = 245.0 KiB | E-60 | [VERIFIED] |
| Idle CPU, busiest core | 9.32 % mean, 9.51 % max (8.6–9.5 % across runs) | E-60, E-56 | [VERIFIED] |
| Idle CPU, both cores | 5.53 % mean (4.7–5.5 % across runs) | E-60, E-56, E-58 | [VERIFIED] |
| Model | 28 024 B, 10 665 params, 212 584 MACs, arena 13 404 B | E-24 | [VERIFIED] |
| L2 keyword end → server | 138 ms median, 196 ms p95 (n = 12) | E-63 | [VERIFIED] + one [INFERRED] term |
| Detection → first audio | 18 ms median, 30 ms p95 | E-63 | [VERIFIED] |
| Recall, held-out session / new speaker | 22/25 / 20/25 | E-35 / E-59 | [VERIFIED] |
| False triggers, quiet / TV + talk | 0.2 /h / 15.8 /h | E-39 / E-51 | [VERIFIED] |
| Stream delivery | 0 overruns, 0 gaps in the final runs | E-60, E-63 | [VERIFIED] |
| Power | not measured | — | [UNVERIFIED] |
