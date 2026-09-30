# System Requirements and Design Constraints {#ch-requirements .chapter}

## Where the requirements come from

Only the problem statement is binding. The project turned it into ten numbered requirements, R1–R10, in `docs/PROJECT_STATE.md` §2; they are reproduced here with their wording checked against the PS text. Everything else — the choice of ESP32-S3, the 6 500 Hz filterbank edge, the 571 ms pre-roll — is a *design decision*, not a requirement, and is labelled as such. [VERIFIED]

Table: Requirements taken from the problem statement {#tab-reqs}
| ID | Requirement (PS wording condensed) | Kind |
|---|---|---|
| R1 | Lightweight, highly accurate KWS model running **locally** on a low-power device | functional |
| R2 | On detection, stream the **subsequent audio** to a **remote ASR server** with minimal data overhead and latency | functional |
| R3 | Evaluated on efficiency (RAM/flash footprint, idle CPU), accuracy (high true-positive rate, near-zero false activations) and latency (keyword end → cloud ASR receiving audio) | evaluation metrics |
| R4 | Proprietary, closed-source or commercial **voice-activation SDKs** are prohibited | software constraint |
| R5 | KWS pipeline built with open-source ML / TinyML frameworks (e.g. TFLite Micro) | software constraint |
| R6 | No models pre-trained on generic assistant keywords; train on a **custom keyword** | software / data constraint |
| R7 | Edge software within **< 256 KB RAM** and **< 10 % CPU** while idling in continuous listening | numeric constraint |
| R8 | Heavy or uncompressed pre-trained transformers are disqualified | software constraint |
| R9 | Evaluated on a physical low-power microcontroller (e.g. Raspberry Pi, ESP32) | hardware constraint |
| R10 | The model must work for the given custom keyword | functional |

:::warn
The PS gives **only two numeric limits**: 256 KB RAM and 10 % idle CPU. It gives **no numeric target** for latency, true-positive rate, false activations per hour, model size, flash size, data overhead or power. This report never invents one. Where a figure is compared with something, it is compared with the PS limit, the architecture study's estimate, or an earlier measurement — and says which.
:::

## Functional requirements

Table: Functional requirements — design response, test and status {#tab-func}
| Req | Why it exists | How the design answers it | How it was tested | Status |
|---|---|---|---|---|
| R1 local KWS | edge "wake-up" avoids cloud cost, privacy loss and delay | int8 DS-CNN (28 024 B) in TFLite Micro on the ESP32-S3, inference every 60 ms | live sessions with scripted prompts; 12/12 in T1 | **Met** [VERIFIED] (E-22, E-35, E-63) |
| R2 stream subsequent audio | the heavy recognition is done remotely | warm TCP, 571 ms pre-roll + live audio until the server's END | integrity (bit-exact), overruns, latency | **Met** [VERIFIED] (E-44, E-60, E-63) |
| R2 minimal overhead | the PS asks for it without a number | PCM16 in 1 280-byte payloads with an 8-byte header; nothing sent while idle except pings | calculated, not measured on the wire | **Met by design** [INFERRED] ([[sec-comm]]) |
| R2 remote ASR | the PS chain ends at "ASR receiving the audio" | self-hosted Vosk en-in-0.5 on a PC | demo run, command sessions | **Met** (receiving); transcript quality limited [VERIFIED] (E-49, E-61) |
| R10 works for the custom keyword | the keyword is the whole point | "Hey Vayro", trained from synthetic + real speech | two speakers, distances 0.5–2 m | **Met with limits** — 2 speakers only [VERIFIED] |

## Measurable constraints

### RAM: < 256 KB

*Why it exists.* To force a genuinely small edge footprint. *The ambiguity.* The PS does not say what counts (the whole device? the application? the model?) or whether KB means 1 000 or 1 024 bytes. *Design response.* The project uses the strictest reading, **S4**: everything in the chip's internal RAM that the application occupies at its peak — global variables, instruction code copied into RAM (IRAM), every task stack, the Wi-Fi and TCP/IP buffers, the tensor arena, the audio ring — with PSRAM disabled so nothing can hide in external memory, and compares it with both 256 000 B and 262 144 B.

*How it is measured.* S4 = static internal RAM from the linker (`idf.py size`: `.bss + .text in IRAM + .data + vectors`) **plus** the peak heap use, computed as the heap's total size minus its lowest free value reported during a run that includes streaming. The 96 KB of on-chip SRAM configured as instruction and data cache is excluded as hardware-reserved (a stated choice, see Chapter 12). *Result:* **250 899 B** — passes 256 000 B by 5 101 B and 262 144 B by 11 245 B. **Met** [VERIFIED] (E-60).

### CPU: < 10 % while idling in continuous listening

*Why it exists.* An always-on device must leave most of the processor free. *The ambiguity.* "10 % CPU" on a dual-core chip can mean the busiest core or both cores averaged; "idle" here means "listening but no keyword", not "doing nothing". *Design response.* All always-on work is on core 1; networking is on core 0; both scopes are reported. *How measured.* FreeRTOS run-time statistics every 10 s (`@CPU`), cross-checked with cycle counters around the front end and inference (`@PERF`). *Result:* busiest core **9.32 % mean, 9.51 % max**; both cores **5.53 %** (E-60); a 12-minute run gave core-1 max 9.04 % (E-56). **Met, with thin margin on the per-core reading** [VERIFIED]. While *streaming* (not idle) core 1 reached 10.5 % — outside the requirement but reported (Chapter 12).

### Latency

*Definition used.* L2 = acoustic end of the keyword → first audio packet received by the server's application. *Target.* None in the PS. *Result.* 138 ms median, 196 ms p95, n = 12 (E-63). **Measured; no pass/fail possible** [VERIFIED, one component estimated].

### Accuracy

*Target.* "High true-positive rate" and "near-zero false activations", no numbers. *Result.* 22/25 and 20/25 keyword prompts; 0.2 false triggers/h in a quiet house, 15.8/h with television and conversation. The quiet figure is close to zero; the household figure is not. **Partially met** [VERIFIED].

### Model and flash size

*Target.* None ("model size (RAM/Flash footprint)" is a scored metric). *Result.* model 28 024 B; tensor arena 13 404 B used of 16 384 B reserved; full firmware image 901 059 B in a 1.5 MB app partition. **Reported** [VERIFIED].

### Power

*Target.* None; the PS says "low-power device" qualitatively. *Result.* **Never measured.** Wi-Fi modem sleep is deliberately disabled for lower latency, which raises consumption [INFERRED]. [UNVERIFIED]

## Software constraints

Table: Software constraints and how compliance is shown {#tab-swc}
| Req | Constraint | Design response | Evidence | Status |
|---|---|---|---|---|
| R4 | no proprietary voice-activation SDK | everything in the audio → features → model → decision path is open source; `tools/forbidden_deps.py` fails the build if ESP-SR, WakeNet, Porcupine, etc. appear anywhere | "forbidden_deps: PASS" in every build log | **Met** [VERIFIED] |
| R4 (strict reading) | nothing closed at all | 9 closed Espressif Wi-Fi/PHY libraries and the boot ROM remain; disclosed in `docs/SBOM.md` | link map | **Disclosed exception** [VERIFIED] |
| R5 | open-source TinyML framework | TensorFlow Lite Micro via esp-tflite-micro 1.4.1, esp-nn 1.4.1 (Apache-2.0) | `dependencies.lock` | **Met** [VERIFIED] |
| R6 | custom keyword, no pre-trained assistant model | "Hey Vayro"; model built layer by layer from random weights (seed 26172); no weight loading anywhere | `model/train/train.py` | **Met** [VERIFIED] |
| R8 | no heavy transformers | edge: 10 665-parameter CNN; server: Kaldi-based Vosk (not a transformer) | SBOM | **Met** [VERIFIED] |

## Hardware constraints

R9 asks for a physical low-power microcontroller; every result in this report comes from one physical ESP32-S3 board with one INMP441 microphone. The ESP32-S3 was the project's choice (the PS says "e.g. Raspberry Pi, ESP32"). The architecture study stated explicitly that if the chip could not meet the limits, "the platform loses, not the requirement"; measurement did not trigger that condition. [VERIFIED]

## Communication requirements {#sec-comm}

The PS asks for "minimal data overhead" without defining it. The design choices and their consequences:

- **Nothing is transmitted while idle** except one clock-synchronisation exchange every 10 s: PING (8-byte header + 8 B), PONG (8 + 24 B) and INFO (8 + 16 B) — 72 bytes of application data, plus TCP/IP headers. [VERIFIED — `netstream.c`]
- **Audio is raw PCM16**: 16 000 samples/s × 2 B = 32 000 B/s of payload. Compression (ADPCM, 4:1) was designed in the study but not built. [VERIFIED]
- **Protocol overhead**: each audio packet carries 1 280 B of audio and an 8-byte header — **0.6 %** at the application layer. With a 40-byte TCP/IP header per packet (one segment per packet, since the configured TCP MSS is 1 440 B and `TCP_NODELAY` is set), the overhead on the network is about **3.7 %**. This figure is calculated, not measured with a packet capture. [INFERRED]
- **Per activation**: a stream of 2.08 s (a keyword with no command, as in T1) carries 66 560 B of audio; a keyword + command of ~3.5 s about 112 kB. [INFERRED from measured stream lengths]

## Environmental and operational constraints

- **One microphone.** No beamforming or echo cancellation is possible; all noise robustness must come from the features, the training data and the decision rule. [VERIFIED]
- **One home, one room layout.** Every recording was made in the same household: a desk with a fan, evening insect/appliance noise (E-34), a television and family conversation (E-51), devotional singing from another room (E-47). This is both the strength (realistic) and the limit (one environment) of the evidence.
- **Home Wi-Fi, fixed server address.** The server's IPv4 address is compiled into the firmware (`CONFIG_PS_SERVER_HOST`). When the router restarted overnight and handed out a different subnet, the device could not reconnect until rebuilt (E-41). [VERIFIED]
- **PC must be awake.** The server runs on a desktop PC; when the PC slept, the server died and streams failed (E-58). [DOCUMENTED]

## Integration requirements

The latency metric can only be measured if the team controls both ends: the device's detection time and the server's receive time. That is why the ASR server is self-hosted and instrumented (microsecond receive timestamps, ping-based clock offset), rather than a commercial cloud API — which would also have raised the open-source question. [VERIFIED — `server/ingest.py`]

## Requirement compliance summary

Table: Compliance at a glance (details in Chapter 12) {#tab-compliance}
| Req | Status | One-line reason |
|---|---|---|
| R1 | Met | 28 KB int8 model runs on the chip, outputs bit-exact with the PC reference |
| R2 | Met | every detection streamed with pre-roll; 0 lost packets in the final tests |
| R3 efficiency | Met | 245.0 KiB peak RAM; idle CPU 9.32 % busiest core / 5.53 % both |
| R3 accuracy | Partially | good recall; false triggers near zero only in a quiet house |
| R3 latency | Measured | 138 ms median keyword end → server (no PS target) |
| R4 | Met, with disclosure | no voice SDK; closed Wi-Fi driver disclosed |
| R5 | Met | TFLite Micro, esp-nn |
| R6 | Met | custom keyword, random initialisation |
| R7 RAM | Met | 5.1 kB margin on the strictest reading |
| R7 CPU | Met | ≈ 0.5 point margin on the busiest core; 4.5 points on the average |
| R8 | Met | no transformer on either side |
| R9 | Met | physical ESP32-S3 |
| R10 | Met with limits | 2 real speakers tested |
