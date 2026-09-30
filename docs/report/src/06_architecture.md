# Complete System Architecture {#ch-architecture .chapter}

## The big picture

The system has three subsystems connected by two links:

1. **The edge device** (ESP32-S3 firmware): captures audio, computes features, runs the keyword model, decides, keeps a short audio history, and streams on demand.
2. **The network**: one Wi-Fi association and one TCP connection on the home LAN.
3. **The ASR server** (Python on a PC): receives streams, timestamps them, ends them when the speaker stops, recognises the command, and records everything.

A fourth element, the **host capture tool** on the same PC, reads the device's USB telemetry. It is not needed for the system to work, but almost all the evidence in this report was collected through it.

!fig #fig-arch figures/architecture.svg | Final architecture. Core 1 runs the always-on audio path inside one task; core 0 runs networking and telemetry. The ring buffer is the only data shared between the two cores. | 100

## Subsystems and their responsibilities

Table: Subsystems of the final system {#tab-subsys}
| Subsystem | Implemented in | Responsibility | Runs where |
|---|---|---|---|
| Audio capture | `firmware/components/audio_capture` | configure I2S0 (MSB framing, 32-bit mono slot, DMA), read 160-sample hops, count overflows | core 1 (called by i2s_reader) |
| Audio ring | `firmware/components/audio_ring` | 0.75 s int16 history; one writer, one reader; detects being overwritten | memory shared by both cores |
| Front end | `firmware/components/microfrontend` | 30 ms window, FFT, 40 mel bands, noise reduction, gain normalisation (PCAN), log → 40 numbers per 10 ms | core 1 |
| KWS engine | `firmware/components/kws_engine` | TFLite Micro interpreter with the int8 model; one inference per call | core 1 |
| Decision logic | `firmware/main/app_main.c` (`kws_on_frame`) | schedule inference every 6 frames, average 3 scores, threshold, refractory, trigger | core 1 |
| Streamer | `firmware/components/netstream` (`streamer_task`) | on a trigger, send START, pre-roll and live audio, END; detect overrun; enforce timeout | core 0 |
| Network link | `netstream` (`net_task`, Wi-Fi events) | Wi-Fi station, TCP connection at boot, reconnect, clock pings, receive END | core 0 |
| Telemetry | `firmware/components/serial_link`, `instrument`, main loop | framed USB messages: `@BOOT @CFG @MEM @KWS @KW @STREAM @STATS @PERF @CPU @NET` | core 0 |
| Ingest + endpointing | `server/ingest.py` (`Session`, `VadEndpointer`) | parse packets, timestamp, answer pings, decide end of speech, write files | PC, receive thread |
| ASR | `server/ingest.py` (`AsrJob`, `AsrFrontEnd`) | condition the audio, run Vosk, produce the transcript | PC, one thread per stream |

## Tasks and cores

Table: FreeRTOS tasks in the product firmware {#tab-tasks}
| Task | Core | Priority | Stack | Created by | Work |
|---|---|---|---|---|---|
| `i2s_reader` | 1 (pinned) | 20 | 3 584 B | `app_main` | the whole audio pipeline, once per 10 ms hop |
| `streamer` | 0 (pinned) | 12 | 4 096 B | `ns_start` | one stream at a time, waits on a 1-slot queue |
| `netlink` | 0 (pinned) | 10 | 4 096 B | `ns_start` | TCP connect/reconnect, pings, receive loop |
| `main` (`app_main`) | 0 | IDF default | 3 584 B | ESP-IDF | boot, then telemetry every 1 s / 10 s and the `T` test hook |
| `wifi` | 0 (pinned by IDF config) | IDF | IDF | ESP-IDF | Wi-Fi driver |
| `tcpip_thread` | either core | 18 | IDF | ESP-IDF | lwIP |
| `esp_timer`, `ipc0/1`, `IDLE0/1` | system | — | — | ESP-IDF | system services and idle accounting |
| `link_tx` | 0 | 5 | 4 096 B | `app_main` | **capture builds only**: sends binary audio/feature frames over USB |

Sources: `app_main.c`, `netstream.c`, product `sdkconfig`. [VERIFIED]

**Why this split.** Everything that must happen every 10 ms without fail is on core 1 at high priority, in a single task, so there is no hand-off between tasks, no extra stacks, and Wi-Fi interrupts on core 0 cannot delay it. The architecture study proposed exactly this split (§4.8), but with three tasks on core 1 (reader, front end + inference, control). The implementation merged them into one: they run strictly one after another on each hop, and splitting would only add context switches and stack memory. [VERIFIED — code; rationale DOCUMENTED in the study §B2]

## Data flow

Follow one piece of sound through the system:

1. **Microphone → DMA.** The INMP441 shifts out a 24-bit sample every 62.5 µs. I2S0's DMA collects 160 of them (10 ms) into one of four buffers.
2. **DMA → int16.** `reader_task` wakes when a buffer is full, takes the 160 32-bit words and keeps bits 31:16 (the top 16 bits of the 24-bit sample).
3. **int16 → ring.** The 160 samples are appended to the 0.75 s ring. Nothing reads them there unless a detection happens.
4. **int16 → features.** The same 160 samples go to the front end, which slides its 30 ms window by 10 ms and outputs 40 numbers. They are converted to int8 and stored as row *f mod 100* of a 100-row feature array.
5. **features → score.** On every sixth frame the 100 rows are copied, oldest first, into the model's input tensor (through a 256-entry lookup table that maps the front end's int8 scale onto the model's), and the model is invoked. Its int8 output becomes a probability *p*.
6. **score → decision.** The mean of the last three *p* values is compared with 0.80, and a trigger is allowed only if at least 2 000 ms have passed since the last one.
7. **decision → stream.** A trigger puts a small record (frame number, ring write position, detection time, raw score) into the streamer's one-slot queue — without waiting. If the streamer is already busy or the network is down, the trigger is logged with `streamed=0`.
8. **ring → network.** The streamer reads the ring from 571 ms before the recorded write position and sends it in 1 280-byte packets; then it keeps up with new audio.
9. **network → server.** The server timestamps every packet, feeds the audio to its voice-activity detector and to the ASR thread, and tells the device to stop when the speaker has finished.

!fig #fig-hop figures/hop_pipeline.svg | What happens inside one 10 ms hop on core 1 (steps ①–⑨ correspond to steps 2–7 above). | 100

## Control flow, initialisation and runtime behaviour

!fig #fig-boot figures/boot_runtime.svg | Left: the boot sequence in `app_main()`. Right: runtime states. Listening never stops; streaming and networking run beside it. | 100

Two design points in the boot sequence deserve attention:

- **The firmware waits for the PC before starting audio** (`link_wait_host(30000)`), because on the native USB port anything printed before the PC opens the port is lost, and the M1 boot diagnostics were the evidence. If no PC opens the port, the wait times out after 30 s and boot continues. For a stand-alone device this is a 30-second delay after every power-up. [VERIFIED — code]
- **The M1 microphone probes still run at every boot** — a 1.3 s stereo probe, four 0.3 s alignment captures, and one or two 0.55 s mono probes — and they decide which slot mask to use. They cost about 3 s of boot time and make each boot print a fresh microphone health check. [VERIFIED — code]

## Communication between device and server

!fig #fig-proto figures/protocol.svg | The TCP message sequence between the device (`netstream.c`) and the server (`ingest.py`), with the latency points measured in T1. | 100

The protocol is binary and minimal. Every message starts with the same 8-byte header — `magic 0xA7`, `flags` (message type), `codec` (always 0 = PCM16), a 16-bit sequence number, and a 24-bit device time in milliseconds. The architecture study's header had no length field, so each message type has a **fixed payload size**, and both sides use a lookup table (`PAYLOAD` in `ingest.py`). The receiver resynchronises on the magic byte if it ever loses track. [VERIFIED]

Table: Message types {#tab-msgs}
| Flag | Name | Direction | Payload | Meaning |
|---|---|---|---|---|
| 0x01 | START | device → server | 32 B | activation number, keyword frame, detection time (µs), pre-roll (571 ms), first ring sample, raw model output |
| 0x02 | CONT | device → server | 1 280 B | 640 PCM16 samples = 40 ms of audio |
| 0x04 | END | device → server | 16 B | activation, samples sent, minimum ring slack, reason (1 server end, 2 device timeout, 3 overrun, 4 socket error) |
| 0x04 | END | server → device | 4 B | activation to stop (server-side endpointing) |
| 0x08 | OVERRUN | device → server | 0 B | the ring was overwritten before it could be sent; followed by END |
| 0x20 | PING | device → server | 8 B | device time t1 |
| 0x80 | PONG | server → device | 24 B | t1, server receive time t2, server send time t3 |
| 0x40 | INFO | device → server | 16 B | current clock offset, round-trip time, number of pings |

**Clock alignment.** Latency across two computers needs a common clock. After each PONG the device computes the offset `((t2 − t1) + (t3 − t4)) / 2` and the round-trip time, and keeps the offset from the lowest-RTT exchange among the last eight (the least disturbed one). It sends that offset with INFO; the server converts the device's detection time into its own clock and reports the uncertainty as half the RTT (1.2–1.8 ms in T1). [VERIFIED — `handle_pong()`]

## External dependencies at runtime

- A Wi-Fi access point with the SSID and password compiled into the firmware (`sdkconfig.wifi`, never committed).
- A server listening on the compiled-in IPv4 address, port 5005.
- For the ASR: the 1.0 GB Vosk model directory on the PC and about 30 s to load it.
- For telemetry and evidence: a PC with the capture tool on the USB port (optional for operation, apart from the 30 s boot wait).

## Failure handling that is actually implemented

Table: What happens when something goes wrong {#tab-failures}
| Failure | Mechanism | Behaviour | Evidence |
|---|---|---|---|
| Streamer falls 0.75 s behind | `backlog >= RING_SAMPLES` or `ring_read` detects it was lapped | sends OVERRUN, stops, END reason 3 — a short correct stream instead of corrupted audio | 3/31 overruns in E-58, all flagged [VERIFIED] |
| Server never ends a stream | device hard timeout | END reason 2 after 10 s | code [VERIFIED] |
| Server always ends a stream | server cap `--stream-s-max 6` | END after 6 s of post-trigger audio | code [VERIFIED] |
| Detection while a stream is open | `ns_trigger()` refuses | logged `streamed=0`; not queued | E-48, E-49 [DOCUMENTED] |
| TCP connection lost | `net_task` loop | closes, waits 1 s, reconnects (2 s pause after each failed connect) | E-41 [DOCUMENTED] |
| Wi-Fi lost | event handler | `esp_wifi_connect()` again | E-41 [DOCUMENTED] |
| Network down for hours | detection is independent of the network | keeps detecting; triggers logged | 5.4 h outage, E-41 [DOCUMENTED] |
| DMA not read in time | driver callback | counted as `i2s_ovf` in `@STATS` (0 in final runs) | E-60 [VERIFIED] |
| Model built for a different front end | `kws_init()` SHA check | refuses to start (`ESP_ERR_INVALID_VERSION`) | code [VERIFIED] |
| USB host not reading | 1 s write timeout | frame dropped and counted (`link_drops`); audio path unaffected | E-20 [DOCUMENTED] |
| Server address unreachable (new subnet) | none | retries forever; needs a rebuild | E-41 — **not handled** [VERIFIED] |
| Heap exhausted | none beyond IDF defaults | not handled; peak measured instead | — [VERIFIED] |

## Operational sequence (final system)

1. **Power and boot.** USB power; the firmware waits for the capture tool (≤ 30 s), prints `@BOOT` (IDF version, firmware hash, chip, PSRAM off), runs the microphone probes (≈ 3 s), initialises the front end with canonical tables and the model (`@KWS … run=v2b … arena_used=13404`), zeroes the ring, starts Wi-Fi.
2. **Connect.** Wi-Fi gets an address (`@NET wifi=up`), the TCP connection opens (`@NET tcp=connected`), eight quick pings establish the clock offset.
3. **Listen.** Core 1 processes 100 hops per second; the model runs 16.7 times per second; the main task prints `@STATS`/`@PERF` every second and `@CPU` every ten.
4. **Detect.** The averaged score crosses 0.80: GPIO15 pulses, `@KW` is printed, the streamer is woken.
5. **Stream.** START, then the 571 ms backlog in about 14 packets, then live 40 ms packets.
6. **End.** The server's VAD decides the command is over and sends END; the device replies with END and its statistics (`@STREAM … reason=1 … min_slack_ms=179`).
7. **Recognise.** The server's ASR thread finishes decoding, prints the command and writes `<stem>.wav`, `<stem>_asr.wav`, `<stem>.json` and a row in `activations.csv`.
8. **Continue.** Listening never paused; the next keyword can be detected two seconds after the previous one.
