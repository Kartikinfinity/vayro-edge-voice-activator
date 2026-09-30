# Hardware–Software Integration and Deployment {#ch-integration .chapter}

## Preparing the hardware

1. **Identify and preserve.** Before anything was flashed, esptool identified the chip (ESP32-S3 rev 0.2, 8 MB in-package PSRAM, 16 MB flash, native USB) and the whole 16 MB flash — an unrelated Arduino-ESP32 sketch built in March 2024 — was backed up to `D:\ps26172_backup\preexisting_flash_16MB.bin`. [DOCUMENTED — PROJECT_STATE §6]
2. **Keep the existing wiring.** The INMP441 was already wired (SCK→GPIO6, WS→GPIO5, SD→GPIO4, L/R→GND). Rather than rewire to the study's pin map, the pins were recorded in `firmware/sdkconfig.board` (C-05).
3. **Choose the link.** The board's USB connector is the S3's native USB-Serial-JTAG (vendor ID 0x303A), not a UART bridge. It became the console and data link (DEC-07); it enumerates as COM7.

## Installing the software

Table: Installation steps and dates {#tab-install}
| When | What | How / where | Evidence |
|---|---|---|---|
| 26 Sep 20:37 | ESP-IDF v5.5.5 (git tag) + toolchain | `D:\esp\esp-idf-v5.5.5`, tools in `D:\esp\.espressif`, installed with Python 3.12 | PROJECT_STATE DEC-01 [DOCUMENTED] |
| 26 Sep | host venv | `D:\ps26172\.venv-host` (numpy, scipy, matplotlib, pyserial) | [DOCUMENTED] |
| 27 Sep 07:33 UTC | training environment | `tools/setup_train_env.sh` in WSL Ubuntu: uv 0.12.19 → CPython 3.12.14 → `~/.venvs/ps26172` → packages from `requirements.lock` | `evidence/m2/setup_train_env.log` [VERIFIED] |
| 27 Sep 07:44 UTC | Piper voices (4 × 63–79 MB) | `tools/get_piper_voices.sh` | `evidence/m2/piper_voices.log` [VERIFIED] |
| 27 Sep | LibriSpeech dev-clean | WSL home folder | `sources.json` [DOCUMENTED] |
| 28 Sep | Vosk 0.3.45 + small en-in-0.4 model | host venv; `D:\ps26172_ext\vosk\` | `evidence/m6_vosk_install.log` [DOCUMENTED] |
| 28 Sep evening | Vosk en-in-0.5 (971 186 187 B) | `D:\ps26172_ext\vosk\vosk-model-en-in-0.5` | E-49 [DOCUMENTED] |

Every download was approved individually by the user before it happened; the approval list is part of the project's working record.

## Building

```powershell
# capture / demo build (streams audio, features and scores over USB)
powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console usbjtag -Port COM7 build flash

# product build — the configuration all final numbers refer to
powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console usbjtag -Port COM7 `
    -ExtraDefaults D:\ps26172\firmware\sdkconfig.product -BuildTag product build flash

# memory report of the last build (static internal RAM, flash)
powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console usbjtag `
    -ExtraDefaults D:\ps26172\firmware\sdkconfig.product -BuildTag product size
```

Before compiling, the wrapper runs the forbidden-dependency gate and regenerates the front-end header; the model source and `sdkconfig.model` must already have been generated with `tools/gen_model_source.py model/artifacts/v2b`. [VERIFIED — `tools/idf.ps1`]

Table: Final product build outputs (`evidence/final_product_size_v2b.log`) {#tab-build}
| Item | Value |
|---|---|
| Application binary `ps26172_fw.bin` | 0xdc030 = 901 168 B (idf_size "total image size" 901 059 B) |
| App partition (single-app "large" table) | 0x177000 = 1 536 000 B → 41 % free |
| Bootloader | 0x5170 = 20 848 B (36 % of its slot free) |
| Flash code (.text) / flash data (.rodata) | 669 272 B / 157 212 B (the model's 28 024 B are in .rodata) |
| Internal RAM, static (DIRAM) | 139 695 B: .bss 65 408 + IRAM .text 54 591 + .data 18 668 + vectors 1 028 |
| Flash size configured / chip size | 4 MB / 16 MB |

The app partition was enlarged from the default 1 MB when the first Wi-Fi + TFLM build reached 926 247 B and left only 12 % free (DEC-21). [VERIFIED]

## Flashing

ESP-IDF's `flash` action calls esptool with the addresses from the partition table; the equivalent command printed by the build is:

```text
python -m esptool --chip esp32s3 -b 460800 --before default_reset --after hard_reset write_flash
    --flash_mode dio --flash_size 4MB --flash_freq 80m
    0x0 bootloader.bin   0x8000 partition-table.bin   0x10000 ps26172_fw.bin
```

esptool verifies a hash of each region after writing ("Hash of data verified" in `evidence/m3_flash_v0.log`). The final product build's own log contains the build and size steps but **not** the flash step, so the evidence that the measured firmware is the built firmware is the firmware's own identity line: every boot prints the first nine hex digits of its ELF's SHA-256.

Table: Which firmware produced which final result {#tab-fwid}
| Run | `@BOOT elf_sha` | Built | Model / threshold / arena / pre-roll | Result |
|---|---|---|---|---|
| E-60 final confirmation | `6294c691f` | 29 Sep 20:21 | v2b / 80 / 16 384 / 571 | RAM, CPU, 30 streams |
| E-61 demonstration (capture build) | `f94cc7e9b` | 29 Sep 22:12 | v2b / 80 / 40 960 / 624 | demo run |
| E-63 T1 latency | `424ec7782` | 30 Sep 08:54 | v2b / 80 / 16 384 / 571 | latency, 12/12 |

The T1 firmware was rebuilt on 30 Sep from unchanged sources (no commit touches `firmware/` after 29 Sep 20:20); its ELF hash differs from E-60's because the build time is embedded in the image. Its `@KWS` and `@CFG` lines are identical to E-60's, and the current `build_usbjtag_product\ps26172_fw.elf` hashes to `424ec77828ffb70e…`, matching T1. [VERIFIED]

## What exactly is deployed

- **Device**: product build of the firmware at commit `9ee1a42` sources (unchanged since), with `sdkconfig.defaults` + `sdkconfig.board` + `sdkconfig.console_usbjtag` + `sdkconfig.model` (v2b: 80 %, N 3, stride 6, 2 000 ms) + `sdkconfig.wifi` + `sdkconfig.product`; model v2b embedded in flash.
- **Server** (T1 command line, from `evidence/server/20260930_085548/server_config.json`):

```text
python -u server/ingest.py --port 5005 --asr D:\ps26172_ext\vosk\vosk-model-en-in-0.5
       --min-after-s 0.8 --stream-s-max 6 --status-file <run folder>\status.txt      (endpoint: vad)
```

The model loaded in 11.7 s on the PC in that run. [VERIFIED]

## Configuration and credentials

The Wi-Fi SSID and password are set in `firmware/sdkconfig.wifi`, which is git-ignored and never committed; `idf.ps1` includes it only if it exists (`-NoNet` builds without networking). Two consequences worth understanding: the credentials end up **inside the firmware image** in flash (anyone with the binary or physical access can read them), and the server address is a compile-time constant (`CONFIG_PS_SERVER_HOST`), so a change of network requires a rebuild (E-41). Traffic is plain TCP on the LAN with no encryption or authentication — the study's deliberate choice to keep a TLS handshake off the latency path and out of the RAM budget. [VERIFIED]

## Memory allocation: where the 245 KiB goes

Static allocations (decided at link time) include the audio ring (`s_buf`, 24 000 B), the tensor arena (16 384 B), the 100 × 40 feature array (4 000 B), the interpreter object, the USB TX pool and all driver globals; the code copied into IRAM (54 591 B) is counted too. Heap allocations happen once at boot. The `@MEM` lines of the final confirmation run show them step by step: [VERIFIED — `runs/20260929_202327_final_v2b_confirm/device_events.jsonl`]

Table: Internal heap during boot and streaming (final firmware, E-60) {#tab-heap}
| After step | Heap free (B) | Change | What was allocated |
|---|---:|---:|---|
| total internal heap | 289 708 | — | internal RAM left after static data, IRAM code and 96 KB of cache |
| boot | 264 032 | −25 676 | USB driver, event queues, IDF start-up |
| front-end init | 252 404 | −11 628 | microfrontend state (FFT buffers, filterbank, noise and PCAN state) |
| model init | 252 404 | 0 | nothing — the arena and interpreter are static |
| network start | 202 248 | −50 156 | NVS, Wi-Fi driver and buffers, lwIP, netlink and streamer stacks |
| reader task started | 194 480 | −7 768 | i2s_reader stack, I2S DMA buffers |
| lowest while streaming | 178 504 | −15 976 | Wi-Fi TX buffers and lwIP segments during 30 streams |

Peak heap use = 289 708 − 178 504 = 111 204 B; S4 = 139 695 + 111 204 = **250 899 B**.

## Debugging and observability interfaces

The system was built to explain itself. Every line the firmware prints over USB starts with a tag and consists of `key=value` pairs; `host/capture.py` turns each into a JSON record with a host timestamp.

Table: Telemetry lines {#tab-telemetry}
| Tag | When | Contents |
|---|---|---|
| `@BOOT` | boot | IDF version, ELF hash, build time, cores, revision, PSRAM flag, flash size, CPU MHz, reset reason |
| `@SYNC`, `@CFG` | boot | time waited for the host; pins, framing, DMA, front-end SHA and parameters; network config |
| `@MEM` | boot steps | internal heap total, free, minimum-ever free, largest block, DMA-capable free, PSRAM policy |
| `@DIAG`, `@ALIGN` | boot | microphone probe statistics, alignment sweep, mono decision |
| `@FETAB` | boot | whether canonical tables were applied; eight table hashes |
| `@KWS` | boot | model name, SHA, size, arena, window, operating point |
| `@NET` | events | Wi-Fi up (IP), TCP connected / failed (errno) / closed |
| `@KW` | each detection | frame, time, score, average, raw output, streamed or not, synthetic flag |
| `@STREAM` | each stream end | reason, audio sent, minimum slack, detection / start / first-audio times, clock offset, RTT |
| `@STATS` | every 1 s | samples, drops, I2S overflows, short reads, level (dBFS), peak, heap free and minimum |
| `@PERF` | every 1 s | stack high-water marks, front-end and inference cycles (mean, max), inference and trigger counts |
| `@CPU` | every 10 s | core 0 / core 1 busy, and the shares of reader, streamer, netlink, wifi, tcpip |

Other debugging hooks: the `T` byte (synthetic trigger, EXP-1), the capture tool's `--send "T@20,T@35"` schedule, stack high-water marks (the reader's measured headroom allowed shrinking its stack from 4 096 to 3 584 B), and the server's `replay_session.py`, which reproduces a live session through the real server code.

## Deployment restrictions (as built)

- The ASR server must run on a PC on the same LAN, at the compiled-in address, awake (a sleeping PC killed the server once, E-58).
- Without a PC reading the USB port, boot waits 30 s before listening.
- No over-the-air update, no provisioning interface, no persistent configuration other than the compiled-in values.
- One stream at a time per device; the server accepts several connections (one thread each) but was only ever tested with one device.
- Plain TCP without authentication: suitable for a trusted LAN only.

## A working-deployment checklist

A correctly deployed product firmware prints, in order: `@BOOT idf=v5.5.5 … emb_psram=0 … cpu_mhz=240`; `@FETAB canonical_tables_applied=1`; `@KWS init=ESP_OK run=v2b model_sha256=f7c913efdbb28f64 … arena_used=13404 … thr_pct=80`; `@CFG net=1 … preroll_ms=571`; `@NET wifi=up`; `@NET tcp=connected`; and the server prints `device connected`. Every `@STATS` line should show `i2s_ovf=0`, and every `@CPU` line core-1 busy below 10 %. [VERIFIED — against the E-60 and T1 logs]
