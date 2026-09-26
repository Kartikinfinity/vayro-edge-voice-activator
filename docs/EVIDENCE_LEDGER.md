# PS26172 — Evidence Ledger

Status vocabulary: **PROVEN** (observed, traceable) · **PRELIMINARY** (physically tested, limited coverage) · **ESTIMATED** (calculated, not measured) · **PROPOSED** (not built/tested) · **BLOCKED** (cannot test; reason given) · **NOT RUN**.
Raw artifacts live under `evidence/runs/<timestamp>_<label>/`. Every plot is generated from a saved file in the same folder.

| ID | Claim | Req | Current basis | Experiment | Acceptance | Status | Artifact | Measured value | Limitations | PPT / video |
|---|---|---|---|---|---|---|---|---|---|---|
| E-01 | Firmware builds from a pinned toolchain; forbidden-dependency gate passes | R4 R5 | [MEAS] build | M0 | green build, gate PASS | **PROVEN** (this host, 2026-09-26) | `evidence/m0/size_uart_m1build.txt` | ESP-IDF v5.5.5, image 241 095 B, gate PASS | local gate, no CI server; clean-checkout rebuild not yet repeated | Compliance |
| E-17 | Static internal-SRAM footprint of the M1 build | R7 | [MEAS] linker | M0 `idf.py size` | report | **PRELIMINARY** (M1 build: no Wi-Fi, no TFLM, includes a 16 KB capture-only TX pool) | `evidence/m0/size_uart_m1build.txt` | DIRAM 93 371 B = IRAM `.text` 60 015 + `.bss` 20 232 + `.data` 12 096 + vectors 1 028 | static only; heap/stacks come from `@MEM` at runtime | Efficiency (C-10) |
| E-02 | INMP441 delivers live 24-bit, 16 kHz audio through I2S0 (Philips, 32-bit slots) | R9 | [HW] compat. §2.2 | M1-A | speech ≥15 dB above room floor; 0 clipped samples in speech; 0 gaps / overflows / drops | NOT RUN | — | — | — | Hardware |
| E-03 | Mic passband edge ≈ 0.423·fs (6 768 Hz) visible at fs = 16 kHz | §2.3b | [HW] DS P-16 | M1-A PSD | attenuation in 7.6–7.95 kHz vs 5.5–6.5 kHz on the broadband segment | NOT RUN | — | — | depends on source spectrum | Front end |
| E-04 | Power-up blanking ≈ 2¹⁸ SCK = 256 ms (P-19) → MIC_SETTLE ≥ 300 ms | §2.3c | [HW]/[EST] | M1 first_nz_ms, cold + warm boot | measured vs 256 ms | NOT RUN | — | — | 1–2 boots only | Engineering detail |
| E-05 | MONO RX slot mode halves DMA traffic (EXP-10) | §2.3a | [ASM] | M1 mono probe | 64 000 vs 128 000 B/s | NOT RUN | — | — | — | Memory |
| E-06 | Speech level at ~0.5 m / ~1 m (dBFS, int16 LSB) → int16 shift decision (C-07) | §2.4 | [EST] −60 dBFS @1 m | M1-A | informational | NOT RUN | — | — | uncalibrated SPL | Front end |
| E-07 | Capture integrity over ≥10 min | data validity | — | M1-B | 0 gaps, 0 CRC-loss, 0 overflows, 0 drops | NOT RUN | — | — | — | Method |
| E-08 | Peak SRAM S0…S4 < 256 KiB with PSRAM disabled | R7 | [EST] 227 KiB (§3.5) | EXP-1 | < 262 144 B and < 256 000 B | NOT RUN | — | — | — | Efficiency |
| E-09 | Idle CPU < 10 % (C1/C2/C3, mean + p99) | R7 | [EST] 2.1–2.8 % (§4.6) | EXP-2 | < 10 % | NOT RUN | — | — | instrument depends on C-06 | Efficiency |
| E-10 | Model flash size and tensor arena | R3 | [EST] 40–60 kB / 32 KiB | M3 | report | NOT RUN | — | — | — | Efficiency |
| E-11 | True-positive rate on held-out real speakers | R3 | — | M3/M4 | report with n | NOT RUN | — | — | — | Accuracy |
| E-12 | False activations per hour on held-out ambient | R3 | — | FA exposure | report with hours + rule-of-three bound | NOT RUN | — | — | exposure-limited | Accuracy |
| E-13 | Latency L1 / L2 / L3 distributions | R3 | [EST] L1 13 ms, L2 205 ms (§10.3) | EXP-7 | report with n | NOT RUN | — | — | — | Latency |
| E-14 | Custom keyword, random init, no pre-trained wake-word model | R6 | [PROP] | provenance record | manifest + training log | NOT RUN | — | — | — | Compliance |
| E-15 | No proprietary voice SDK in the build; residual Wi-Fi blob disclosed | R4 | [PROP] | X25 gate + SBOM | gate PASS, SBOM complete | NOT RUN | — | — | Wi-Fi MAC/PHY blob (§6.5) | Compliance |
| E-16 | Keyword → stream → ASR transcript end-to-end on physical hardware | R2 | [PROP] | M6 | transcript correct | NOT RUN | — | — | — | Demo video |
