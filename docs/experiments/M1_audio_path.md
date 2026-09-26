# M1 — Physical audio path

**Purpose.** Prove the INMP441 → I2S0 → ESP32-S3 path delivers correct audio before anything consumes it.
**Hypotheses.** (H1) Live, unclipped, gap-free 24-bit audio at 16 kHz with 32-bit Philips slots. (H2) The PSD falls off above ≈0.423·fs = 6 768 Hz (DS P-16). (H3) The first ~256 ms after I2S clock start are digital zeros on a cold power-up (P-19). (H4, EXP-10) MONO slot mode delivers 64 000 B/s instead of 128 000 B/s.

**Configuration.** Firmware `firmware/` (M1 build), ESP-IDF v5.5.5, 240 MHz, PSRAM off. I2S0 master, std Philips, 32-bit data/slot, 16 kHz, BCK 1.024 MHz, 4 × 160-frame DMA descriptors, MCLK unused. Pins from `firmware/sdkconfig.board`. Link: CRC-framed serial (921 600 baud on a UART bridge, or native USB-Serial-JTAG).

**Instrumentation.** On device: stereo probe (per-slot RMS, DC, peak, low-byte activity, first non-zero sample after clock start), mono probe (byte rate, RMS), 1 s `@STATS` (I2S overflows, pool/link drops, level, heap, stack high-water marks). On host: `host/capture.py` (sample-index gap detection, CRC), `host/analyze_audio.py` (level, clipping, zero runs, Welch PSD, spectrogram).

**Procedure.**
- *Session A (20 s, cold boot):* unplug/replug USB (cold power-up for H3), then `capture.py --reset --seconds 20`. Script: 0–5 s silence · 5–12 s normal speech at ~0.5 m (count 1–10) · 12–16 s steady "shhhh" at ~0.3 m · 16–20 s speech at ~1 m.
- *Session A′ (warm boot):* repeat with `--reset` only (no replug) → warm blanking value.
- *Session B (10 min):* room left as-is → integrity + first ambient data.

**Metrics and acceptance.**
| Metric | Acceptance |
|---|---|
| Speech segment RMS − silence segment RMS | ≥ 15 dB |
| `clip_samples_24` in speech / hiss segments | 0 |
| Host gaps, CRC-loss gaps, device `i2s_ovf`, `pool_drops`, `link_drops` | all 0 |
| Zero runs ≥ 1 ms after the start-up blanking | 0 |
| `rolloff_db` on the hiss segment | < −3 dB (informational: depends on the source spectrum) |
| Blanking `first_nz_ms` | reported vs 256 ms (no pass/fail) |
| Mono byte rate | reported (64 000 vs 128 000 B/s) |

**Raw data preserved.** Whole run folder: WAVs (24-bit and derived int16), `device_log.txt`, `device_events.jsonl`, `boot_raw.txt`, `capture_summary.json`, `analysis.json`, PNGs.

## Results

*NOT RUN.*
