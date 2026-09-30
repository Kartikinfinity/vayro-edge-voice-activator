::: html
<section class="titlepage">
<div class="kicker">Technical reconstruction report · personal study edition</div>
<div class="ttl">Hey Vayro: a low-latency wake-word activator on an ESP32-S3</div>
<div class="sub">The complete engineering history and final state of the PS 26172 prototype — research basis, hardware, firmware, model, server, every validation test, what failed, what was fixed, and what is still open.</div>
<div class="rule"></div>
<table class="meta">
<tr><td>Problem statement</td><td>SIH 2026 · PS 26172 (ISRO, Department of Space) — "Low Latency and Efficient Voice Activator for Edge Devices" · Category: Hardware · Theme: Smart Automation</td></tr>
<tr><td>Team</td><td>DATA_Edgepulse (AUC-SIH26-172041)</td></tr>
<tr><td>System</td><td>ESP32-S3 + INMP441 microphone · keyword "Hey Vayro" · int8 DS-CNN on TensorFlow Lite Micro · Wi-Fi/TCP stream · Vosk (Kaldi) ASR server</td></tr>
<tr><td>Reconstructed from</td><td>repository <code>D:\ps26172</code> at commit <code>@@COMMIT@@</code> (30 Sep 2026), evidence ledger E-01…E-63, raw run folders under <code>evidence/</code>, and the two documents supplied at the start: the PS text and the Track C architecture study</td></tr>
<tr><td>Date</td><td>30 September 2026</td></tr>
</table>
<div class="foot">Every number in this report comes from a file in the repository, and the file is named next to it. Headline measurements were re-computed from the raw logs for this report, not copied from summaries. Where evidence is missing or weaker than a claim would need, the report says so with an explicit label. This is an engineering study document; it deliberately contains no presentation material.</div>
</section>
<!--TOC-->
:::

# Executive Technical Summary {#executive-summary .front}

**What was built.** A two-part voice activation system. An ESP32-S3 microcontroller with an INMP441 digital microphone listens all the time. Every 10 ms it turns the last 30 ms of sound into 40 log-mel numbers, and every 60 ms a 10 665-parameter int8 depthwise-separable CNN (DS-CNN) scores the last 1.02 s of those numbers for the custom keyword **"Hey Vayro"**. When the mean of three consecutive scores reaches 0.80, the device starts streaming audio — beginning 571 ms *before* the detection, so the keyword's tail and anything said straight after it are included — over a TCP connection that was opened at boot. A Python server on a PC decides when the speaker has finished (energy-based voice-activity detection), and transcribes the command with the open-source Vosk (Kaldi) recogniser. Nothing leaves the device until a detection happens. [VERIFIED]

**Final configuration.** Product firmware (`firmware/sdkconfig.product`: decisions DEC-22 and DEC-24), model **v2b** at threshold 0.80 (SHA-256 `f7c913efdbb28f64…`, decision DEC-26), ESP-IDF 5.5.5, esp-tflite-micro 1.4.1 with esp-nn 1.4.1, and the threaded ASR server with Vosk `en-in-0.5`. [VERIFIED]

Table: Headline results on the final configuration (all re-checked against the raw files) {#tab-headline}
| Quantity | Result | Conditions | Evidence |
|---|---|---|---|
| Peak internal RAM (S4, strictest scope) | **250 899 B = 245.0 KiB** | while streaming; PSRAM disabled; static 139 695 B + peak heap 111 204 B | E-60 [VERIFIED] |
| Idle CPU, busiest core (core 1) | **9.32 % mean, 9.51 % max** | 18 windows of 10 s, Wi-Fi + TCP up, FreeRTOS run-time stats | E-60 [VERIFIED] |
| Idle CPU, both cores averaged | **5.53 % mean** | same run | E-60 [VERIFIED] |
| Model | 28 024 B int8, 10 665 parameters, 212 584 MACs, arena 13 404 B | weights stay in flash | E-24, E-60 [VERIFIED] |
| Keyword end → audio at the ASR server (L2) | **138 ms median, 196 ms p95** | T1: n = 12, one speaker, LAN, capture term 10 ± 7 ms estimated | E-63 [VERIFIED], part [INFERRED] |
| Detection → first audio at the server | 18 ms median (p95 30 ms) | same | E-63 [VERIFIED] |
| Keyword detection, speaker 1, held-out session | **22 / 25** prompts (0.5–2 m) | live on device; speaker 1 is also in the training data | E-35 [VERIFIED] |
| Keyword detection, new speaker | **20 / 25** prompts | speaker never used in training | E-59 [VERIFIED] |
| False triggers, quiet night | **1 in 5 h** (0.2 /h) | declared held-out hours | E-39 [VERIFIED] |
| False triggers, household with TV and talk | **39 in 2.47 h (15.8 /h)** | offline replay equal to the device's live triggers | E-51 [VERIFIED] |
| Streamed audio integrity | 23/23 streams bit-exact; 30/30 and 12/12 streams without loss | E-44, E-60, E-63 | [VERIFIED] |
| Train/deploy feature parity | 12 000 / 12 000 frames bit-exact | device vs host twin | E-21 [VERIFIED] |

**The engineering that mattered most.** Six results shaped the final system and are explained in Chapters 10–13:

1. The microphone data was captured one bit late with the textbook I2S framing; a measured alignment sweep switched the firmware to MSB-justified framing (E-18).
2. Device features differed from training features in 3 of 5 998 frames because the chip's maths library rounds differently from the PC's; the host's tables are now copied into the device, making them bit-identical (E-21, DEC-16).
3. The first "product" build used 260.2 KiB — over the limit — once instruction code in internal RAM was counted; configuration trims brought the streaming peak to 245.0 KiB (E-42, E-52, E-53, E-60).
4. The server's speech recogniser blocked its own network reads, which backed audio up into the device and caused 3 of 31 streams to overrun; moving recognition to its own thread fixed it (E-58, E-60).
5. A fourth model (v4) passed its pre-declared selection rule but failed badly on the first new speaker (14/25 vs 20/25), so the team shipped v2b in a documented override (E-59, DEC-26).
6. The final latency test on the exact shipped configuration gave 138 ms, replacing an earlier 95 ms figure measured on a different build without the recogniser running (E-37, E-63).

**Main limitations.** False triggers with TV or family speech (15.8 per hour) are the largest open problem. Only two real speakers were tested. The busiest core's idle margin is about half a percentage point, and while streaming it reaches 10.5 %. Part of the latency (the "capture term") is estimated, not measured, and no logic analyser was available. Power was never measured. The server address is compiled into the firmware, and the firmware waits up to 30 s for a USB host at boot. The ASR's word accuracy is that of an off-the-shelf model (publisher WER 36 %). **This is a working, physically tested prototype, not a production-ready product** (Chapter 14).

# How to Read This Report {#reading-guide .front}

## Evidence labels

Every statement that a reader might need to trust is marked with one of six labels. They are stricter than normal writing, on purpose.

Table: Evidence labels used throughout {#tab-labels}
| Label | Meaning in this report |
|---|---|
| [VERIFIED] | Checked directly during this reconstruction: read in the source code, or re-computed from the raw run files. |
| [DOCUMENTED] | Stated in the project's own records (evidence ledger, state record, commit messages) but not re-derived for this report. |
| [INFERRED] | A reasonable interpretation of the evidence that no file states directly. The reasoning is given. |
| [UNVERIFIED] | The evidence is not enough to confirm the claim. |
| [PLANNED] | Proposed in a design document or plan but not built. |
| [FUTURE] | Suggested in this report as later work (Chapter 15). Not built. |

The project's own ledger (`docs/EVIDENCE_LEDGER.md`) uses a second vocabulary — PROVEN, PRELIMINARY, ESTIMATED, PROPOSED, BLOCKED, NOT RUN — and the supplied architecture study uses tags such as [HW], [EST] and [MEAS]. Those words appear in quotations from those documents; the six labels above are this report's own verdicts.

## Identifiers you will meet

- **R1–R10** — the ten requirements taken from the problem statement (Chapter 3).
- **M0–M6** — the milestones of the build plan (toolchain, audio, front end, local KWS, trigger, stream, ASR).
- **EXP-n** — experiments defined in the architecture study (EXP-1 memory, EXP-2 CPU, …).
- **E-nn** — rows of the evidence ledger; each points to raw files.
- **DEC-nn** — implementation decisions recorded in `docs/PROJECT_STATE.md`; **C-nn** — conflicts and open issues recorded there.
- **X-nn**, **P-nn**, **H-nn**, **M-nn**, **AMB-nn** — failure modes, microphone facts, SoC facts, module facts and ambiguities as numbered in the architecture study.
- **S01**, **S02** — the two real speakers who recorded test sessions. **v0…v4** — the six trained models (v2a and v2b are two variants of v2).

## Sources that were available, and sources that were not

Available and used: the problem-statement PDF (`D:\sih final\sih 2026  (1).pdf`); the architecture study `PS26172_TRACK_C_HARDWARE_ARCHITECTURE.md` (1 810 lines, dated 12 Sep 2026); the complete git repository (50 commits, 26–30 Sep 2026); the evidence ledger, state record, SBOM and consistency sheet; every raw run folder under `evidence/`.

**Not available:** the "Master Spec", "Track A" and "Track B" documents that the architecture study cites throughout; the vendor datasheets it quotes (their facts are used here only as the study quotes them); any official SIH guidelines. No peer-reviewed research paper was supplied — the architecture study is the research document this project was built from (Chapter 2).

## Units and conventions

- **KiB** = 1 024 bytes and **kB** = 1 000 bytes. The PS says "256KB" without defining it, so memory is always checked against both 262 144 B and 256 000 B.
- **"Core 1 busy"** is 100 % minus the share of time core 1 spent in its idle task, measured by FreeRTOS over 10 s windows. **C3** is the mean of the two cores.
- Times of day are local (IST). "p95" is the 95th percentile.
- File paths are relative to the repository root `D:\ps26172` unless they start with a drive letter.

## Deliberately left out

This is not a presentation. The submission slides, the demonstration video and any advice on presenting are excluded. Where the demonstration run produced technical evidence (E-61), its measurements are reported like any other test.
