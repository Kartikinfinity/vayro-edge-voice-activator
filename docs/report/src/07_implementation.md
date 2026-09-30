# Implementation and Source-Code Walkthrough {#ch-implementation .chapter}

This chapter is a map for reading the repository. It starts with the directory structure, then follows the firmware in the order it executes, and then covers the model pipeline, the server, the host tools and the test scripts. Line counts and names are taken from the files at commit `@@COMMIT@@`. [VERIFIED throughout unless marked]

## Repository structure

```text
D:\ps26172\
├── firmware\                     ESP-IDF project (the edge software)
│   ├── CMakeLists.txt            project "ps26172_fw"
│   ├── sdkconfig.defaults        policy: 240 MHz, PSRAM off, 1 kHz tick, run-time stats, caches, -O2
│   ├── sdkconfig.board           wiring (BCK 6, WS 5, SD 4) and I2S framing (MSB)
│   ├── sdkconfig.console_*       console on UART or native USB
│   ├── sdkconfig.model           GENERATED operating point (threshold 80 %, N 3, stride 6, 2 000 ms)
│   ├── sdkconfig.product         EXP-1 product configuration (DEC-22, DEC-24)
│   ├── sdkconfig.wifi            local credentials — git-ignored, never committed
│   ├── dependencies.lock         esp-tflite-micro 1.4.1 / esp-nn 1.4.1 with hashes
│   ├── main\  app_main.c (670), Kconfig.projbuild (122), idf_component.yml
│   └── components\
│       ├── audio_capture\        I2S0 receive (71)
│       ├── audio_ring\           unified ring buffer (43)
│       ├── microfrontend\        wrapper (99 + 94) + GENERATED config/tables + vendored TFLM/KissFFT
│       ├── kws_engine\           TFLM interpreter (79) + GENERATED model_data.c (the model bytes)
│       ├── netstream\            Wi-Fi, TCP, streaming, clock sync (333)
│       ├── serial_link\          CRC-framed USB link (174)
│       └── instrument\           @BOOT / @MEM lines (72)
├── model\
│   ├── frontend.json             SINGLE SOURCE OF TRUTH for the features
│   ├── frontend\                 host twin: psfe.py, build_twin.sh, parity_test.py, export_tables.py …
│   ├── data\                     sources.json (data manifest + declared splits), gen_tts.py, build_dataset.py
│   ├── train\                    train.py, export.py, run_v4.sh
│   ├── eval\                     eval_stream.py (device-identical replay) + 10 analysis scripts
│   ├── env\                      requirements.lock, check_converter.py
│   └── artifacts\                v0 … v4 models, metrics, logs, evaluation JSONs, selection rules
├── server\                       ingest.py (453) + latency_report, stream_integrity, replay_session, ASR tests
├── host\                         capture.py (501), analyze_audio.py, prompter.py, t1_session.py,
│                                 scripts\*.txt (recording protocols), demo recording tools
├── tools\                        idf.ps1, forbidden_deps.py, gen_frontend_config.py, gen_model_source.py, setup scripts
├── docs\                         PROJECT_STATE.md, EVIDENCE_LEDGER.md, SBOM.md, experiments\, submission\, report\
└── evidence\                     raw data: runs\<time>_<label>\, server\<session>\, build/size logs
```

The **source of truth** for anything numerical is in three places: `model/frontend.json` (features), `model/artifacts/<run>/metrics.json` + `selection_*_outcome.json` (model and operating point), and `firmware/sdkconfig.*` (everything else on the device). Generated files are never edited by hand; each says so in its first line.

## Build entry points

The firmware is always built through `tools/idf.ps1`, never with a bare `idf.py`. The wrapper does four things before calling ESP-IDF:

1. puts Python 3.12 first on the PATH and sources IDF's `export.ps1`;
2. runs `tools/forbidden_deps.py` — the build stops on any hit;
3. runs `tools/gen_frontend_config.py` — regenerates `ps_frontend_config.h` from `frontend.json` only if it changed (keeping the file's timestamp stable avoids needless rebuilds);
4. assembles the `SDKCONFIG_DEFAULTS` list and deletes the build's `sdkconfig` if any defaults file is newer, because ESP-IDF would otherwise keep the old values silently.

Build variants live in separate folders: `build_usbjtag` (capture/demo build), `build_usbjtag_product` (the final product build, `-ExtraDefaults firmware\sdkconfig.product -BuildTag product`), `build_usbjtag_nonet` (no Wi-Fi), `build_uart`.

The model enters the firmware through `tools/gen_model_source.py <artifact folder>`: it checks that `metrics.json` describes exactly that `.tflite` (SHA-256), writes the bytes as a 16-byte-aligned `const` array (so they stay in flash), writes the model's SHA-256 and the front-end SHA-256 its training data used, computes the 256-entry input lookup table *exactly* as the evaluation code does, and writes `sdkconfig.model` from the matching selection outcome.

## Firmware, in execution order

### `app_main()` — boot (firmware/main/app_main.c)

`app_main` runs once on core 0. In order:

1. `link_init()` installs the USB-Serial-JTAG driver and redirects every `ESP_LOG` call into framed TEXT messages, so logs can never corrupt binary audio frames.
2. `link_wait_host(30000)` blocks until the PC sends a byte (the capture tool sends `S` when it opens the port) or 30 s pass.
3. `inst_boot_report()` prints `@BOOT` (IDF version, first 9 hex digits of the firmware ELF hash, build date, cores, chip revision, PSRAM flag, flash size, CPU MHz, reset reason); `@CFG` prints the pins, framing and DMA layout; `inst_mem_report("boot")` prints heap totals.
4. **Microphone probes.** `probe()` opens I2S in a given slot mode, discards a settling period, then accumulates per-slot statistics (`slot_stats_t`): mean (DC), RMS, peak, the fraction of words with any of the low 8 bits set (`lowbyte_nz`, which must be ~0 because the INMP441 drives only 24 bits), the fraction whose 24-bit LSB is 1 (`lsb1`, ~50 % when correctly aligned), zeros, and the first non-zero sample after the clock started. The stereo probe runs first so it sees the first clock after boot; `alignment_sweep()` repeats it for Philips/MSB × normal/inverted bit clock and prints `@ALIGN`; the mono probe (EXP-10) then confirms which slot mask carries the microphone.
5. `ps_fe_init()` builds the front end from the constants generated from `frontend.json`; then, only if `ps_fe_tables_fe_sha256` equals the firmware's `PS_FE_JSON_SHA256`, `ps_fe_set_tables()` overwrites the filterbank weights and PCAN lookup table with the host twin's canonical values, and `@FETAB` prints eight table hashes for comparison with the PC.
6. `kws_init()` loads the model (next section) and `@KWS` prints its identity: `run=v2b model_sha256=f7c913efdbb28f64 model_bytes=28024 arena_bytes=16384 arena_used=13404 win=100 bands=40 stride=6 avg_n=3 thr_pct=80 refractory_ms=2000`.
7. `ring_init()` zeroes the ring; `ns_start()` starts NVS, Wi-Fi and the two network tasks on core 0.
8. `xTaskCreatePinnedToCore(reader_task, "i2s_reader", CONFIG_PS_READER_STACK, …, 20, …, 1)` starts the audio pipeline on core 1 at priority 20.
9. The main loop wakes every second: prints `@STATS` (samples, drop counters, I2S overflows, level in dBFS, heap free and heap minimum) and `@PERF` (stack high-water marks, front-end and inference cycle counts, trigger count); every tenth second calls `cpu_report()`; and polls the USB link for a `T` byte, which starts a stream exactly like a detection but marked `synthetic=1` — the hook that made memory and transport tests possible without speaking (EXP-1).

### `reader_task()` — the always-on pipeline

This is the most important function in the firmware. Its loop body, lightly abridged:

```c
if (ac_read(raw, sizeof raw, &got, 1000) != ESP_OK || got != sizeof raw) { s_short_reads++; continue; }
gpio_set_level(CONFIG_PS_INST_ACTIVE_GPIO, 1);          /* I-1 duty-cycle pin: start of this hop's work */
for (int i = 0; i < HOP; i++) i16[i] = (int16_t)(raw[i] >> 16);   /* bits 23:8 of the 24-bit sample */
ring_write(i16, HOP);                                    /* pre-roll source for the streamer */
const uint32_t c0 = esp_cpu_get_cycle_count();
while (off < HOP) {                                      /* at most one feature frame per hop */
    const int produced = ps_fe_process(i16 + off, HOP - off, &used, feat);
    off += used; if (produced) { fi = fe_frames++; new_frame = 1; }
}
const uint32_t dc = esp_cpu_get_cycle_count() - c0;     /* front-end cycles (I-2) */
if (new_frame) kws_on_frame(fe_frames - 1, feat);       /* inference + decision, timed separately */
/* … level meter, capture-build framing … */
gpio_set_level(CONFIG_PS_INST_ACTIVE_GPIO, 0);
```

*Problem it solves:* do all periodic work in one place so its cost is exactly the "idle listening" CPU. *Inputs:* 160 × int32 words per call. *Outputs:* ring contents, one feature frame, possibly a trigger. *Why this design:* the hop is the natural clock; one task on one core cannot be pre-empted by Wi-Fi; the cycle counter brackets give per-stage attribution. *Tested by:* feature parity (E-21), posterior parity (E-22), live-equals-replay (E-26), and the CPU runs (E-43, E-56, E-60).

The `>> 16` deserves a note. The microphone's 24-bit sample sits in bits 31:8 of the 32-bit I2S word; shifting right by 16 keeps bits 31:16, i.e. the top 16 bits of the sample. The host capture tool derives its int16 files as `int24 >> 8`, which is the same value, so device and PC always see identical 16-bit audio. The measured room floor was about 52 units RMS in this representation, so quantisation noise is about 45 dB below it and the truncation costs nothing measurable (DEC-09).

### `kws_on_frame()` — scheduling, smoothing, decision

```c
if (f < KWS_WIN - 1 || (f - (KWS_WIN - 1)) % CONFIG_PS_KWS_STRIDE_FRAMES) return;   /* every 6th frame */
for (int i = 0; i < KWS_WIN; i++) kws_set_row(i, s_fring[(f - (KWS_WIN - 1) + i) % KWS_WIN]);
const float p = kws_invoke(&raw, &cyc);
ring_p[n_inf % CONFIG_PS_KWS_AVG_N] = p; n_inf++;
/* avg = mean of ring_p[0..N-1] */
if (avg >= CONFIG_PS_KWS_THRESHOLD_PCT / 100.0f &&
    (!any_trig || f - last_trig_frame >= CONFIG_PS_KWS_REFRACTORY_MS / PS_FE_HOP_MS)) {
    /* trigger: GPIO15 high for one frame, @KW line, ns_trigger({frame, ring_w(), t_detect, raw}) */
}
```

Three details make the device's behaviour reproducible on the PC:

- The 100-row feature array `s_fring` is a circular buffer of int8 rows; `kws_set_row` writes each row straight into the model's input tensor through the lookup table (the "zero-copy" change from EXP-1 that removed a separate 4 KB window buffer).
- The three-score average starts from zeros, exactly like `np.convolve(p, ones(3)/3, "full")` in `eval_stream.py`, so the first detections after boot match the offline replay (E-26: 27 of 27 trigger times identical).
- `t_ms = 30 + 10·f` — the time of the last sample in frame *f*'s window — is printed with every `@KW` so detections can be located in recorded audio.

### `audio_capture.c` — I2S

`ac_open()` creates an I2S0 receive channel in master role with `dma_desc_num = 4` and `dma_frame_num = 160`, a standard-mode slot configuration for 32-bit data (MSB or Philips template from `sdkconfig.board`), the three GPIOs, no MCLK, and registers `on_recv_q_ovf` to count DMA overflows. `ac_read()` is a thin wrapper around `i2s_channel_read()`. Keeping this component small made it easy to reopen the channel with different framings during the M1 sweep.

### `audio_ring.c` — the unified ring buffer

```c
static int16_t s_buf[RING_SAMPLES];            /* CONFIG_PS_RING_MS * 16 samples = 12 000 in the product */
static _Atomic uint32_t s_w;                   /* monotonic write index (wraps at 2^32) */

void ring_write(const int16_t *x, size_t n) {
    uint32_t w = atomic_load_explicit(&s_w, memory_order_relaxed);
    for (size_t i = 0; i < n; i++) s_buf[(w + i) % RING_SAMPLES] = x[i];
    atomic_store_explicit(&s_w, w + (uint32_t)n, memory_order_release);   /* publish after the data */
}
int ring_read(uint32_t idx, int16_t *dst, size_t n) {
    /* 0 if not written yet, or if already overwritten (lapped); copy; re-check after copying */
}
```

The indices are *sample counts since boot*, not array positions, so "571 ms before the trigger" is simply `w − 9136`, and "has the writer overtaken me?" is `w − idx > RING_SAMPLES`. The release/acquire atomics make the one-writer (core 1), one-reader (core 0) pattern safe without a mutex on the audio path, and the reader checks again after copying because the writer may lap it mid-copy. It implements the architecture's "retention is a property of not overwriting yet" idea (§8.4). The front end does not need a ring cursor: it consumes the fresh hop directly.

!fig #fig-ring figures/ring_preroll.svg | The ring at the moment of a detection, and what the streamer does with it. | 100

### `microfrontend/` — features

`ps_frontend.c` is a 99-line wrapper around the vendored TensorFlow Lite Micro "microfrontend". `ps_fe_init()` fills a `FrontendConfig` with **every** parameter from `frontend.json` — window 30 ms, step 10 ms, 40 channels, 125–6 500 Hz, filterbank output shift 7, noise-reduction smoothing (10 bits, 0.025 / 0.06, minimum remaining 0.05), PCAN on (strength 0.95, offset 80, 21 gain bits), log scale shift 6 — because the upstream defaults are different (25 ms window, PCAN off) and relying on them would be a silent mismatch. `ps_fe_process()` returns at most one frame per call. `ps_frontend_diag.cc` computes an FNV-1a hash of every table the library builds at init (window, filterbank tables, PCAN lookup, FFT twiddles) and can read or overwrite the two libm-dependent tables — the mechanism behind the M2 parity fix. The int8 conversion used by the model,

```c
static inline int8_t ps_fe_to_int8(uint16_t v) {
    int32_t q = (((int32_t)v * 256) + 333) / 666 - 128;       /* TFLM micro_speech mapping */
    return (int8_t)(q < -128 ? -128 : (q > 127 ? 127 : q));
}
```

is defined in the header so that the firmware and `psfe.py` (`to_int8`) use literally the same arithmetic.

### `kws_engine.cc` — TensorFlow Lite Micro

```c
constexpr size_t kArenaBytes = CONFIG_PS_KWS_ARENA_BYTES;          /* 16 384 in the product build */
alignas(16) uint8_t g_arena[kArenaBytes];                           /* static internal RAM */
tflite::MicroMutableOpResolver<6> g_resolver;                        /* only the ops the model uses */
…
if (std::strcmp(g_kws_model_fe_sha256, PS_FE_JSON_SHA256) != 0) return ESP_ERR_INVALID_VERSION;
g_resolver.AddConv2D(); g_resolver.AddDepthwiseConv2D(); g_resolver.AddReshape();
g_resolver.AddFullyConnected(); g_resolver.AddLogistic();
g_interp = new (g_interp_mem) tflite::MicroInterpreter(model, g_resolver, g_arena, kArenaBytes);
```

The interpreter object is placed in static memory with placement `new`, so nothing comes from the heap at run time. Only five operator kernels are registered, which keeps the flash image small and makes it impossible for a model with any other operator to load. `kws_invoke()` brackets `Invoke()` with the CPU cycle counter and converts the int8 output to a probability with the output tensor's scale and zero point (1/256 and −128 for every model here). Because esp-tflite-micro links esp-nn, the convolutions run on the S3's vector-optimised kernels without any code here asking for them.

### `netstream.c` — Wi-Fi, TCP and the streamer

- `wifi_init()` initialises NVS (erasing it once if the partition holds an incompatible layout — the pre-existing Arduino image left one), creates the default station interface, registers an event handler that reconnects on every disconnect, applies the SSID/password from Kconfig, starts Wi-Fi and disables modem sleep.
- `net_task()` waits for an IP address, opens the TCP socket to `CONFIG_PS_SERVER_HOST:5005`, sets `TCP_NODELAY` and a 100 ms receive timeout, then loops: send a PING when due (8 at 0.5 s intervals, then every 10 s), receive, resynchronise on the magic byte, handle PONG (`handle_pong`) and server END. On any error it closes the socket, waits, and reconnects.
- `streamer_task()` blocks on a one-slot queue. For each trigger:

```c
uint32_t r = t.trig_sample - (uint32_t)CONFIG_PS_PREROLL_MS * 16;   /* first sample to send */
send_pkt(F_START, 0, &st, sizeof st);
while (ok) {
    if (s_server_end) { reason = 1; break; }                            /* server endpointing */
    if (esp_timer_get_time() > t_stop) { reason = 2; break; }          /* 10 s hard timeout */
    const uint32_t backlog = ring_w() - r;
    if (backlog >= RING_SAMPLES) { send_pkt(F_OVERRUN, seq, NULL, 0); reason = 3; break; }
    if (backlog < PKT_SAMPLES) { vTaskDelay(pdMS_TO_TICKS(5)); continue; }   /* wait for 40 ms of audio */
    if (!ring_read(r, pcm, PKT_SAMPLES)) { /* lapped while copying: OVERRUN */ }
    send_pkt(F_CONT, seq++, pcm, sizeof pcm); r += PKT_SAMPLES;
}
send_pkt(F_END, seq, &en, sizeof en);   /* activation, samples sent, minimum slack, reason */
```

It records the minimum ring slack seen during the stream and the device time of the first audio packet, both printed in `@STREAM`. `ns_trigger()` is non-blocking and refuses when not connected or already streaming — the "one stream at a time" policy.

### `serial_link.c` and `instrument.c` — the evidence channel

Frames are `A5 5A 26 17 | type | flags | length (u16) | payload | CRC-16/CCITT-FALSE`. Types: 1 audio (24-bit samples), 2 text, 3 feature frames, 4 model outputs (capture builds only). The USB write uses a 1 s timeout — a 100 ms timeout once lost a frame when Windows stalled — and a mutex so tasks cannot interleave frames. Text lines are limited to 240 characters (one telemetry line once lost its tail, so `@STATS` was split into `@STATS` and `@PERF`). `instrument.c` produces `@BOOT` and `@MEM`; `@MEM` reports internal-heap total, free, minimum-ever free and largest block, plus `psram=disabled_in_sdkconfig`.

### `cpu_report()` — how the CPU figure is produced

Every 10 s the main task calls `uxTaskGetSystemState()`, which returns each task's accumulated run time. The difference since the last call, divided by the elapsed run-time ticks, gives each task's share; **core busy = 100 % − idle task share** for `IDLE0` and `IDLE1`. The same line gives the shares of `i2s_reader`, `streamer`, `netlink`, `wifi` and `tcpip_thread`. Interrupt time is charged to whichever task was interrupted, so time spent in interrupts during idle is slightly under-counted — a documented limitation (E-43).

### Configuration options (Kconfig)

Table: Project configuration options: defaults and the final product values {#tab-kconfig}
| Option | Default | Product | Meaning |
|---|---:|---:|---|
| `PS_I2S_BCK/WS/SD_GPIO` | 4 / 5 / 6 | 6 / 5 / 4 | wiring (sdkconfig.board) |
| `PS_I2S_FORMAT` | Philips | **MSB** | measured framing |
| `PS_CAPTURE_STREAM` | y | **n** | binary audio/feature/posterior frames over USB |
| `PS_LINK_TX_RING` | 16 384 | 2 048 | USB driver transmit buffer (bytes) |
| `PS_KWS_ARENA_BYTES` | 40 960 | **16 384** | tensor arena |
| `PS_KWS_STRIDE_FRAMES` | 6 | 6 | inference every 60 ms |
| `PS_KWS_AVG_N` | 3 | 3 | scores averaged |
| `PS_KWS_THRESHOLD_PCT` | 90 | **80** | generated from the selection outcome |
| `PS_KWS_REFRACTORY_MS` | 2 000 | 2 000 | minimum time between triggers |
| `PS_RING_MS` | 1 000 | **750** | ring length |
| `PS_PREROLL_MS` | 624 | **571** | audio sent from before the trigger |
| `PS_READER_STACK` | 4 096 | 3 584 | i2s_reader stack (measured high-water mark allowed it) |
| `PS_STREAM_MAX_MS` | 10 000 | 10 000 | device-side stream timeout |
| `PS_WIFI_PS_NONE` | y | y | modem sleep off |
| `PS_NET_ENABLE` | n | y | Wi-Fi streaming (enabled when `sdkconfig.wifi` exists) |
| `PS_SERVER_HOST` / `PORT` | 192.168.1.100 / 5005 | the PC's LAN address / 5005 | compiled-in server address |
| `PS_MIC_SETTLE_MS` | 300 | 300 | settle time before the stereo probe measures |

The **capture (demo) build** keeps the defaults for `PS_CAPTURE_STREAM`, `PS_LINK_TX_RING`, `PS_KWS_ARENA_BYTES`, `PS_RING_MS`, `PS_PREROLL_MS` and `PS_READER_STACK`, and has none of the product memory trims (DEC-22, DEC-24): it streams audio, features and model outputs over USB so that sessions can be recorded and replayed, with a 1.0 s ring, a 624 ms pre-roll and a 40 KiB arena. This matters when reading any number: E-60 and E-63 are product-build numbers; the demonstration run (E-61) and most recording sessions used the capture build, whose idle CPU is about 1–2 points higher because of the USB audio traffic.

## Model pipeline code (summary; details in Chapter 8)

Table: Training and evaluation scripts {#tab-modelcode}
| File | Role |
|---|---|
| `model/frontend/psfe.py` | ctypes wrapper of `libpsfe.so`; `Frontend().features(int16)` gives the device's features; `to_int8()` the device's mapping |
| `model/frontend/build_twin.sh` | compiles the firmware's front-end C files into `libpsfe.so` in WSL |
| `model/data/gen_tts.py` | Piper TTS generation with spelling fixes, speed/prosody randomisation, speaker-disjoint split |
| `model/data/build_dataset.py` | mixes clips into device-recorded room audio, computes twin features, cuts 1 s windows, labels by keyword end, adds real, hard and household negatives |
| `model/train/train.py` | builds the DS-CNN, trains with SpecAugment masks and class weighting, first int8 export, metrics |
| `model/train/export.py` | re-exports with a static batch-1 graph so only 5 operator types appear |
| `model/eval/eval_stream.py` | replays recordings exactly as the device would (reference kernels, same LUT, stride, averaging, refractory); keyword-end location; prompt scoring |
| `model/eval/prompt_hits.py`, `household_compare.py`, `event_scan.py`, `fa_context.py` | per-prompt hits, household false activations, event listing |
| `model/eval/posterior_parity.py`, `eval_device_triggers.py` | device vs host model outputs; live triggers vs offline replay |

## Server code

`server/ingest.py` (453 lines) is built from five pieces:

- **`AsrFrontEnd`** — conditions audio for the recogniser only: an 8th-order 150 Hz high-pass filter (removes fan rumble) and a *fixed* gain per stream chosen so that the loudest speech in the pre-roll (the keyword itself, 95th percentile of 50 ms levels in 300–4 000 Hz) sits at −20 dBFS, clamped to 0.5–40×. It holds back the first 571 ms until the gain is known; because the pre-roll arrives as one burst, this adds no measurable delay.
- **`VadEndpointer`** — decides when the command is over: 20 ms frames in 300–4 000 Hz; threshold = keyword level − 20 dB (not below −60 dBFS); speech starts after 3 loud frames; END after 0.7 s of quiet, or after 1.5 s if speech never started.
- **`AsrJob`** — one thread per activation with its own Vosk recogniser, fed through a queue; produces the transcript after the device's END. This is the 29 Sep fix that took ASR off the receive path (E-58).
- **`Session`** — per connection: parses packets, answers PING with PONG using `time.perf_counter_ns()`, tracks sequence gaps, computes `L1_start` and `L1_audio0` in server time, requests END (only after `--min-after-s` 0.8 s of post-trigger audio, or at the 6 s cap), and writes files under a lock. Files are named `c<HHMMSS>_act<NNNN>` with the connection time because the device restarts activation numbers at every reboot and plain names once overwrote ten activations (E-36).
- **`serve()` / `main()`** — accept loop with a 1 s timeout (so Ctrl+C works on Windows), one thread per connection, model loading, and `--print-style compact` / `--status-file` for supervised sessions.

The analysis scripts next to it are the measurement instruments: `latency_report.py` (L1, lag and L2 per activation — see Chapter 10), `stream_integrity.py` (finds each server WAV inside the device's own USB recording and checks it sample by sample), `replay_session.py` (feeds a recorded session through the *real* `Session` class to test server changes offline), and `asr_level_test.py` / `make_asr_control.py` / `asr_offline.py` (the controlled ASR experiments of E-45).

## Host tools

- **`host/capture.py`** (501 lines) — opens the USB port without toggling reset lines, resets the board reliably (a Windows driver quirk required esptool's DTR/RTS sequence, E-20), parses frames, writes `audio_24bit.wav`, `audio_16bit.wav`, `features_device.bin`, `posteriors_device.bin`, `device_log.txt`, `device_events.jsonl` (every `@` line as JSON with a host timestamp) and `capture_summary.json`. It detects missing samples from the sample index in each audio frame and **writes zeros for them rather than hiding them**, rotates files every hour for long recordings, starts a new file set if the device reboots, runs at high process priority, auto-resets after a link stall, shows scripted prompts (`--script-file`), and can send timed bytes such as the synthetic trigger (`--send "T@20"`).
- **`host/analyze_audio.py`** — levels, clipping, zero runs, Welch PSD with the pass-band edge marked, spectrograms (M1 evidence).
- **`host/prompter.py`**, **`host/t1_session.py`** — prompt windows with wall-clock logs; T1 starts the server and the capture hidden, waits for the board to connect, then shows the prompts.
- **`host/scripts/*.txt`** — the recording protocols: keyword sessions v1/v2 (25 keyword prompts at 0.5/1/2 m including fast, slow and soft, plus 16 confusable words and free talk), command sessions v1–v3, and the T1 latency script.
- Demo-recording tools (`demo_take.py`, `demo_cut90.py`, `term.py`, `prompt_window.py`, …) produce the demonstration video; they do not affect the system and are not described further.

## Where the tests live

There is no unit-test framework and no CI server; testing is done by scripts that compare two independent computations of the same thing, run on recorded or live data.

Table: Test and verification scripts {#tab-tests}
| Script | Compares | Kind of test | Main result |
|---|---|---|---|
| `firmware` probes + `@ALIGN` | four I2S framings on live audio | hardware validation | E-18 |
| `model/frontend/parity_test.py` | device features vs host twin on the same audio | integration (train/deploy parity) | E-21 |
| `model/frontend/compare_tables.py` | device vs host init-table hashes | diagnostic | E-21 |
| `model/eval/posterior_parity.py` | device int8 outputs vs TFLite reference on the PC | integration (deployment parity) | E-22 |
| `model/eval/eval_device_triggers.py` | live device triggers vs offline replay | integration (decision logic) | E-26 |
| `model/eval/eval_stream.py`, `prompt_hits.py`, `household_compare.py` | detections vs scripted prompts / hours of audio | accuracy and reliability | E-25…E-59 |
| `server/stream_integrity.py` | server WAVs vs device USB recording | end-to-end integrity | E-44 |
| `server/latency_report.py` | server receive times vs device detection times + audio | performance | E-37, E-62, E-63 |
| `server/replay_session.py` | server code on recorded sessions | regression | E-48, E-58 |
| `model/frontend/selftest_twin.py`, `model/env/check_converter.py` | smoke tests | environment | — |
