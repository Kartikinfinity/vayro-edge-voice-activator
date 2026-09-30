# Final System State and Limitations {#ch-final-state .chapter}

## Snapshot as of 30 September 2026

The complete chain — microphone, features, model, decision, pre-roll streaming, server endpointing and recognition — exists and has run on physical hardware. The product configuration has been measured for memory, idle CPU, streaming reliability and latency; the model has been tested on two real speakers and about 13 hours of real household audio. The code is at commit `@@COMMIT@@`; the firmware sources have not changed since 29 Sep 20:20.

Table: Feature and subsystem status {#tab-status}
| Feature / subsystem | Implementation status | Validation evidence | Remaining issue |
|---|---|---|---|
| I2S capture (MSB framing, mono, DMA) | complete | alignment sweep, 10 h capture with 1 gap of 20 ms (E-18, E-40) | root cause of the Philips offset not isolated |
| Front end (microfrontend, canonical tables) | complete | 12 000/12 000 bit-exact (E-21) | CPU cost 4.5 % (fixed-point FFT, NR, PCAN) |
| KWS model v2b on TFLM + esp-nn | complete | 1 984/1 984 outputs bit-exact (E-22) | windowed, not streaming: inference 3.9 % CPU |
| Decision logic (mean-3 ≥ 0.80, 2 s refractory) | complete | live = replay 27/27, 39/39, 12/12 | threshold chosen on one speaker's validation session |
| Keyword detection accuracy | functional | 22/25 held-out session, 20/25 new speaker, 12/12 T1 | only 2 real speakers; misses with no pause before a command |
| False-trigger behaviour | functional, weak in speech | 0.2 /h quiet, 15.8 /h TV + talk (E-39, E-51) | **main open problem** |
| Unified ring + pre-roll 571 ms | complete | min slack 169–179 ms; 0 overruns in final runs | slack ≈ 180 ms: sensitive to server/network stalls |
| Wi-Fi + warm TCP + clock sync | complete | 30/30, 12/12 streams; offset ±1.2–1.8 ms | server address compiled in; no TLS; credentials in flash |
| Stream protocol (START/CONT/END/OVERRUN) | complete | 23/23 bit-exact (E-44) | PCM only (no ADPCM); one stream at a time |
| Server ingest + VAD endpointing | complete | END by VAD in all T1 streams | rule tuned in one room |
| ASR (Vosk en-in-0.5, conditioning, thread) | complete | 3/4 commands exact in the demo; 2/5 in a noisy test | recogniser accuracy (publisher WER 36 %) |
| Memory within 256 KB (strict S4) | complete | 250 899 B (E-60) | ≈ 5 kB margin; heap peak depends on network load |
| Idle CPU < 10 % | complete | 9.32 % busiest core, 5.53 % both (E-60) | ≈ 0.5-point margin; 10.5 % while streaming |
| Latency instrumentation (L1, L2) | complete | T1: 138 / 196 ms (E-63) | 10 ms capture term estimated; n = 12; no L3 |
| Telemetry and evidence tooling | complete | used for every result | — |
| Compliance gate, SBOM, licence | complete | gate PASS in every build | closed Wi-Fi/PHY driver (disclosed); two NC training voices |
| GPIO duty-cycle / detection-pulse measurement | code only | never captured | needs a logic analyser |
| Streaming (stateful) model | not implemented | — | [PLANNED] (DEC-11) |
| ADPCM, UDP, speculative streaming, TLS | not implemented | — | [PLANNED] in the study only |
| Bounded-heap enforcement ("arena discipline") | not implemented | — | reporting only |
| Power measurement | not done | — | [UNVERIFIED] |
| Stand-alone operation (no PC on USB) | partially | — | 30 s boot wait; the server still needs a PC |

## What is fully implemented

The firmware's capture, front end, model, decision, ring, Wi-Fi/TCP client, stream protocol, clock synchronisation and telemetry; the server's ingest, endpointing, conditioning, threaded recognition and recording; the host capture and analysis tools; the complete training pipeline (TTS generation, dataset construction, training, int8 export, device-identical evaluation, selection); and the compliance tooling.

## What is partially implemented

- **Instrumentation:** the GPIO signals for duty cycle and detection exist but were never read; the run-time statistics became the primary CPU instrument.
- **Continuous integration:** the architecture's seven CI gates exist as scripts (parity, forbidden dependencies, memory from the size report) but only the dependency gate runs automatically; there is no CI server.
- **Stand-alone deployment:** the device works without the USB host after a 30 s wait, but it has no way to learn a new server address or network.

## Physically tested versus tested in software only

**Physically tested on the device:** microphone path and framing; feature parity (device features compared with the PC); model output parity; live detection on scripted sessions (S01 sessions 2 and 3, S02, command sessions, T1, demonstration); 10 h and 2.5 h live listening; memory and CPU on the product build; streaming, overruns, latency; network outage behaviour.

**Tested in software only (offline replay):** every comparison between models (v0–v4) other than the one running live at the time; false-activation rates of models that were not on the device during the recording; threshold sweeps. These are legitimate *because* live-equals-replay was verified on three recordings — but they are still simulations of the device, not the device.

## What has not been verified

- The capture-term portion of latency (≈ 10 ms, estimated).
- Behaviour on a congested or different network; L3 (catch-up) latency.
- Any speaker other than S01 and S02; any room other than one home; children's voices; accents beyond those represented by the TTS voices.
- Power consumption.
- Long-duration stability of the *product* build (the longest product run is 12 minutes; the 10 h run used the capture build).
- The physical board details (maker, breadboard, pull-down resistor).

## Known limitations

1. **False triggers with television or conversation (15.8 /h)** — roughly one every four minutes in a lively household; each sends a few seconds of room audio to the server.
2. **Speaker coverage** — one speaker in training; one additional speaker tested.
3. **Thin CPU margin on core 1** (≈ 0.5 point idle) and > 10 % while streaming; inference time varies with Wi-Fi activity.
4. **Thin RAM margin** (≈ 5 kB on the 256 000 B reading).
5. **Fixed network configuration** — server address and Wi-Fi credentials are compiled in; no encryption or authentication.
6. **ASR quality** — the recogniser is an off-the-shelf open model; command recognition is not reliable enough for real control.
7. **Latency evidence is modest** — 12 activations, one speaker, one session.
8. **Boot behaviour** — 30 s wait without a USB host; ≈ 3 s of microphone diagnostics on every boot.

## Dependencies required to run the system

Hardware: the ESP32-S3 board with the INMP441 wired as in [[tab-wiring]]; a 2.4 GHz Wi-Fi network; a PC on the same LAN. Software: ESP-IDF 5.5.5 and the pinned components to rebuild; Python 3.12 with numpy, scipy and vosk 0.3.45, and the 1 GB Vosk en-in-0.5 model, for the server; the WSL training environment only to retrain.

## What would have to change for larger-scale deployment

- **Robustness of detection** across many speakers, rooms and televisions — a much larger real dataset and a held-out test set of many speakers; possibly a second-stage verifier on the server that can reject false triggers (the audio is already there).
- **Configuration and provisioning** — Wi-Fi and server settings stored in NVS and set without rebuilding; server discovery; no dependence on a USB host.
- **Security** — authenticated, encrypted transport (TLS established at boot, as the study advised, with the RAM budget re-checked); no credentials in the firmware image.
- **Fleet operations** — over-the-air updates, device identity, remote logging, crash reporting.
- **Server** — a scalable ASR service (many concurrent streams), monitoring, and a proper command-understanding layer.
- **Hardware** — a production PCB with the microphone's recommended pull-down and decoupling, and measured power in the intended power mode.

:::warn
**Prototype, not product.** Everything in this report shows that the *architecture* works on the chosen hardware within the PS's limits, with honest measurements. It does not show that the device is ready for real homes: the false-trigger rate in normal household conditions, the two-speaker evidence, the fixed network configuration and the absence of security are each individually disqualifying for a product.
:::
