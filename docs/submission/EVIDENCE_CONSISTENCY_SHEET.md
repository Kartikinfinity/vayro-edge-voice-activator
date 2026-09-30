# Evidence & Consistency Sheet — PS 26172 (Hey Vayro)

Built 30 Sep 2026 from the actual files: the built PPT (`docs/submission/PS26172_SIH2026_Idea.pptx`, text extracted from its
XML), the 90 s demo (`evidence/demo/PS26172_demo_90s.mp4` and the raw logs of its two takes), and the project documents
(`docs/EVIDENCE_LEDGER.md` E-01…E-62, `docs/PROJECT_STATE.md`, `docs/SBOM.md`, `docs/DEMO_RUNBOOK.md`, model metrics,
firmware configs, build map). Nothing in the PPT or the video was changed.

Status key: **VERIFIED** (measured or directly checkable, evidence cited) · **PROVISIONAL** (true only with a caveat,
estimate, or single weak run) · **INCONSISTENT** (conflicts with another place or with evidence) · **UNSUPPORTED** (no
evidence). Where: S1–S6 = PPT slides; V = demo video (V-A = 0–68 s demo build, V-B = 68–90 s product firmware);
D = project documents.

New analysis done for this sheet (no new tests): latency re-computed for the final configuration (E-62, after fixing a
file-name bug in `server/latency_report.py` that had made it skip all post-28-Sep sessions); closed libraries listed from
the final firmware's link map; capture-build idle CPU quantified from the 2.5 h household run (822 windows); training code
checked for weight loading; all 9 reference links checked (HTTP 200, arXiv titles match).

---

## A. Master table of claims

### A1 Platform and pipeline

| ID | Claim (where) | Value | Measures / conditions | Evidence | Status |
|---|---|---|---|---|---|
| C01 | ESP32-S3 N16R8, 240 MHz, PSRAM off (S3; V `@BOOT`) | 240 MHz; PSRAM disabled | chip config | `@BOOT cpu_mhz=240 emb_psram=0`, `@MEM psram=disabled_in_sdkconfig` (E-60 run, V) | VERIFIED |
| C02 | INMP441, I2S, 16 kHz, 24-bit (S3) | 16 kHz, 24-bit capture, int16 = word >> 16 | mic path | E-02, E-18, `sdkconfig.board` | VERIFIED |
| C03 | Wiring SCK→GPIO6, WS→GPIO5, SD→GPIO4 (S3) | pins | board | `sdkconfig.board`; your message 26 Sep | VERIFIED |
| C04 | "on a breadboard" (S3) | — | physical build | none | **UNSUPPORTED** (not confirmed) |
| C05 | ESP-IDF 5.5.5 / FreeRTOS (S3; V) | v5.5.5 | toolchain | `@BOOT idf=v5.5.5`, E-01 | VERIFIED |
| C06 | 40-band log-mel every 10 ms, 30 ms window (S2, S3) | 30/10 ms, 40 bands, 125–6500 Hz | front end | `model/frontend.json`, `@CFG fe_…` (V) | VERIFIED |
| C07 | Scores "the last 1 s every 60 ms" (S2, S3) | window 100 frames (1.02 s), stride 6 frames (60 ms) | inference cadence | `@KWS win=100 stride=6` (V) | VERIFIED (1 s is rounded from 1.02 s) |
| C08 | Decision: mean of 3 ≥ 0.80, 2 s refractory (S2, S3) | N=3, thr 0.80, 2000 ms | shipped operating point v2b | `firmware/sdkconfig.model`, `@KWS avg_n=3 thr_pct=80 refractory_ms=2000` (V) | VERIFIED |
| C09 | TensorFlow Lite Micro + ESP-NN (S2, S3) | esp-tflite-micro 1.4.1, esp-nn 1.4.1 | runtime | `firmware/dependencies.lock` | VERIFIED |
| C10 | Bit-exact train/device feature pipeline, 12 000 / 12 000 frames (S2, S3) | 12 000/12 000 (+3 001/3 001, 8/8 table hashes) | parity test after DEC-16 | E-21; device outputs = host model 1 984/1 984 (E-22) | VERIFIED |
| C11 | Custom keyword, trained from scratch / random init (S2, S3) | — | model provenance | `model/train/train.py` builds layers, no weight loading, seed 26172; `metrics.json` | VERIFIED by code — **ledger E-14 still says "NOT RUN"** (stale) |
| C12 | No proprietary voice SDK (S5) | gate PASS | build-time scan (ESP-SR, WakeNet, MultiNet, Picovoice…) | `forbidden_deps: PASS` in `evidence/final_product_build_v2b.log`, `demo_capture_build_v2b.log` | VERIFIED — **ledger E-15 still says "NOT RUN"** (stale) |

### A2 Model and memory

| ID | Claim (where) | Value | Measures / conditions | Evidence | Status |
|---|---|---|---|---|---|
| C13 | 10.7 k parameters / 10 665 (S2, S3) | 10 665 | DS-CNN v2b | `model/artifacts/v2b/metrics.json` | VERIFIED |
| C14 | 212 584 MACs per inference (S3) | 212 584 | per 1 s window | same | VERIFIED |
| C15 | 28 KB int8 model / 28 024 B (S2, S3, S4) | 28 024 B (27.4 KiB, 28.0 kB) | flatbuffer in flash | `metrics.json`; `@KWS model_bytes=28024` (V) | VERIFIED |
| C16 | Tensor arena 13 404 B / 13.4 KB (S2, S3, S4) | 13 404 B used | arena of 16 KiB (product) / 40 KiB (demo build) | `@KWS arena_used=13404` (E-60, V-A and V-B) | VERIFIED — V shows `arena_bytes=40960` (V-A) and `16384` (V-B): allocated vs used, both correct |
| C17 | 5 ops (S3) | CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, LOGISTIC, RESHAPE | int8 graph | `metrics.json` | VERIFIED |
| C18 | Peak RAM while streaming 245.0 KiB (< 256 KB) (S2, S4; D runbook) | 250 899 B = 245.0 KiB | final product firmware v2b: static DIRAM 139 695 B + peak heap 111 204 B during 30 streams; cache SRAM excluded | E-60 (single run); E-53 same design 249 615 B | VERIFIED (2 runs: 243.8–245.0 KiB) |
| C19 | Memory trims saved 9.6 KB (S4) | 9 640 B | DEC-24 before/after | E-52 → E-53 | VERIFIED |
| C20 | Whole firmware image (not claimed) | 901 059 B | flash image, product build | `evidence/final_product_size_v2b.log` | VERIFIED (available if "flash footprint" is asked) |

### A3 CPU

| ID | Claim (where) | Value | Measures / conditions | Evidence | Status |
|---|---|---|---|---|---|
| C21 | Idle CPU 5.5 %, both cores (S2, S4, S5) | 5.53 % mean (max 5.72) | mean of both cores, idle listening, Wi-Fi+TCP up, final firmware, 18 × 10 s | E-60; other runs 4.72 % (E-58, v4 same arch), 4.82 % (E-56, 12 min) | VERIFIED — worst of the runs (conservative) |
| C22 | Busiest core 9.5 % / "max core 9.5 %" (S2, S4) | 9.51 % max (mean 9.32) | core 1 (audio + model task) | E-60; range across runs 8.6–9.5 % (E-43, E-56, E-58, E-60, V-B) — rises with Wi-Fi traffic | VERIFIED |
| C23 | V-B: product firmware core1_busy 8.77 / 8.79 % | 8.77, 8.79 % | same product firmware, silent room | take `20260929_221050_efficiency_term`, server session `221052` (0 streams) | VERIFIED; consistent with C22 |
| C24 | V-A: demo build core1_busy 10.62–11.40 % (visible on screen) | 10.62–11.40 % | **capture build** (mic audio sent over USB for the video) + live streaming | capture build idle core 1 = **10.87 %** mean (10.43–11.23, n = 822, household run 28 Sep); with a stream 11.54 % mean | VERIFIED as a fact about the demo build — **INCONSISTENT-looking** next to the PPT's ≤ 9.5 % unless explained |

### A4 Streaming and latency

| ID | Claim (where) | Value | Measures / conditions | Evidence | Status |
|---|---|---|---|---|---|
| C25 | 571 ms pre-roll, 0.75 s ring (S2, S3) | 571 ms / 750 ms | product firmware | `sdkconfig.product`; `@CFG preroll_ms=571` (V-B) | VERIFIED — V-A shows `preroll_ms=624` (demo build ring 1.0 s) |
| C26 | 40 ms packets, warm TCP link (S3) | 1 280 B = 640 samples | protocol | DEC-21, E-32 | VERIFIED |
| C27 | "0 bytes of audio sent until the keyword is detected" (S5) | 0 | design: audio only inside activations | ingest logs; silent take: 0 streams in 80 s (V-B) | VERIFIED — **but a false trigger also sends audio** (see C39) |
| C28 | 32 kB/s, only from keyword to end of command (S5) | 32 000 B/s payload (+8 B header per 1 280 B = 32.2 kB/s) | 16 kHz × 16 bit; stream = 571 ms pre-roll + until end of speech (VAD) or 6 s cap | protocol, `ingest.py` | VERIFIED |
| C29 | Commands spoken with no pause are "never clipped" (S2) | — | pre-roll 571 ms vs detection lag | detection lag ≤ 144 ms (E-37), ≤ 164 ms (E-62); keyword end inside pre-roll 22/24 (E-36, 624 ms build); demo transcripts captured commands (E-61) | **PROVISIONAL** ("never" is absolute; evidence is design + small n) |
| C30 | Streams arrive complete (V: "0 lost") | 0 lost packets; bit-exact | TCP streams | E-44 (23/23 bit-exact), E-60 (30/30, 0 overruns), E-61 | VERIFIED |
| C31 | "1.7 ms detection → first packet at server" (S4) | 1.66 ms median (E-37); 1.8–1.9 ms (E-62) | **stream-start control message** (no audio) | E-37, E-62 | VERIFIED number — **misleading label**: evaluators will read "first packet" as first audio |
| C32 | "first audio at the server ≈ 2 ms after detection" (S2) | 2.12 ms median | only without ASR load (27 Sep, non-ASR server) | E-37 | **INCONSISTENT** with the final setup and the demo: with the ASR server running median 6.7 / 7.1 / 10.6 ms, p95 15–42, max 57 (E-62; V-A shows +6.5…+7.6, +57.4 ms) |
| C33 | "keyword end → server ≈ 95 ms median, 136 ms p95" (S2, S4) | 95.4 / 136.3 ms, max 164 (n = 22) | 27 Sep, capture build v2b, non-ASR server, keyword-only prompts; L2 = measured detection lag (84 ms median) + L1 + 10 ± 7 ms estimated capture term | E-37 (reproduced 30 Sep) | VERIFIED **for that configuration**; final configuration with ASR: 81 ms median, 172 ms p95 (n = 9, E-62, PROVISIONAL); product firmware + real keywords: NOT RUN |

### A5 Accuracy

| ID | Claim (where) | Value | Measures / conditions | Evidence | Status |
|---|---|---|---|---|---|
| C34 | "22 / 25 held-out prompts, speaker 1, 0.5–2 m" (S4) | 22/25 (88 %); confusables 2/16 | S01 session 3, recorded after v2b was frozen; **S01 is also in training (session 1)** → held-out session, not held-out speaker | E-35 | VERIFIED (1 session) — label must say "held-out session" |
| C35 | "20 / 25 new speaker, never trained on" (S4) | 20/25 (80 %); 0.5 m 10/12, 1 m 6/8, 2 m 4/5; confusables 1/16 | S02, one session; v2b replayed offline on the device recording (bit-exact pipeline, E-22/E-26) | E-59 | VERIFIED (1 session) |
| C36 | "1 in 5 h false triggers, quiet night (held-out)" (S4) | 1 FA / 5 h = 0.2 /h (95 % upper ≈ 0.95 /h) | c005–c009 of the 27 Sep night, household asleep | E-39 — which states it **must not be quoted as the general rate** | VERIFIED only when paired with C37 |
| C37 | "TV / family speech still triggers: 15.1 per hour" (S4) | 15.1 /h (13 FA / 0.86 h) | v2b on the held-out part used for the v4 comparison | E-51/E-55. **v2b never trained on household audio, so the whole 2.47 h is held-out for v2b: 39 FA = 15.8 /h**; 27 Sep evening 27 FA / 2 h = 13.5 /h (E-39) | **INCONSISTENT choice**: the larger, equally valid exposure gives 15.8 /h |
| C38 | "cut this to 10.4 /h (model v4)… v4 lost new-speaker recall (14/25)" (S4) | 9 FA / 0.86 h; 14/25 | same held-out audio as 15.1 /h | E-55, E-59 | VERIFIED (the comparison must use 15.1 vs 10.4 on the same audio) |
| C39 | Privacy: "the room is only heard by the chip until someone says Hey Vayro" (S5) | — | — | false triggers stream room audio: 0.2 /h quiet, ~14–16 /h with TV | **INCONSISTENT** with C36/C37 |
| C40 | Demo: 4/4 prompted keywords detected, 0 triggers while talking without the keyword (V-A) | 4/4 (+1 repeat); 0 in ~12 s of talk | one take | E-61 | VERIFIED (small n) |
| C41 | "two speakers (plus TTS voices in 4 accents)" (S4) | 2 real speakers; 4 TTS voice models | S01, S02; voices en_US libritts_r, en_GB vctk, en_US l2arctic (non-native English), hi_IN pratham | E-35, E-59; `docs/SBOM.md` §4 | VERIFIED speakers — "4 accents" is loose wording |

### A6 ASR

| ID | Claim (where) | Value | Measures / conditions | Evidence | Status |
|---|---|---|---|---|---|
| C42 | Vosk en-in: 36 % WER published (S4) | 36.12 % | publisher's figure on NPTEL | alphacephei.com/vosk/models | VERIFIED (publisher's number) |
| C43 | Demo transcripts (V-A) | 3 of 4 commands exact ("turn on the light", "what time is it", "open the door"); "play some music" heard as "openly to" / "place your music" | one take, 30–50 cm | E-61 | VERIFIED; own earlier WER 39 % (E-49, TV on, 5 streams) |

### A7 Compliance, licensing, openness

| ID | Claim (where) | Value | Evidence | Status |
|---|---|---|---|---|
| C44 | "Only open-source components" (S2) | — | final firmware links closed Espressif Wi-Fi/PHY libraries: `libnet80211`, `libpp`, `libcore`, `libmesh`, `libespnow`, `libsmartconfig`, `libwapi` (esp_wifi), `libphy`, `libbtbb` (esp_phy) — from `firmware/build_usbjtag_product/ps26172_fw.map`; plus chip mask-ROM routines | **INCONSISTENT** with S6 and SBOM |
| C45 | "the one closed Wi-Fi radio blob … disclosed" (S6) | — | same map: a set of closed radio-driver libraries, not one blob | PROVISIONAL wording ("one blob" undercounts) |
| C46 | "no vendor SDK or licence fee" (S5) | — | two training voices are CC BY-NC / BY-NC-SA → weights trained with them are not free for commercial use (`docs/SBOM.md` §4) | **INCONSISTENT** ("licence fee" part) |
| C47 | Our code Apache-2.0 (S6) | — | `LICENSE` | VERIFIED |
| C48 | References [1]–[9] (S6) | 9 | links return HTTP 200; arXiv 1711.07128 and 1804.03209 titles match | VERIFIED |

### A8 Impact, estimates, process

| ID | Claim (where) | Value | Evidence | Status |
|---|---|---|---|---|
| C49 | Hardware ≈ ₹1 000 (estimate) (S5) | ₹1 000 | none (no BOM) | **UNSUPPORTED** |
| C50 | "front end for any ESP32-class device" (S5) | — | only ESP32-S3 tested; ESP-NN speed-ups target the S3 | **UNSUPPORTED** |
| C51 | ISRO labs, smart automation, assistive use (S5) | — | potential uses, untested | PROVISIONAL (must read as potential) |
| C52 | "no cloud cost while idle / while listening" (S2, S5) | — | no audio sent or processed while idle; the server machine still runs | PROVISIONAL wording |
| C53 | Power not yet measured (S5) | — | true | VERIFIED |
| C54 | "a new keyword = new recordings + the same scripts" (S5) | — | pipeline is scripted; never demonstrated for a second keyword | PROVISIONAL |
| C55 | "Selection rules declared before each test / written and committed before each held-out test" (S2, S3, S6) | — | rules committed before tests (E-30, selection_rule_v3/v4); v2 rule amended before held-out use; **v4's rule was overridden by DEC-26** on new-speaker evidence | PROVISIONAL (true, but one documented override must be mentioned) |
| C56 | "60 logged evidence entries, each … with its raw data" (S2, S6) | now 62 | E-08…E-16 are early plan rows still marked NOT RUN / FAILING without raw data | **INCONSISTENT** (count stale; 9 rows stale) |
| C57 | "every number traceable to an evidence log" (S5) | — | true once the contradictions below are fixed | PROVISIONAL |
| C58 | Demo "shows keyword → stream → transcript live on this board" (S3) | — | E-61 | VERIFIED |

---

## B. Contradictions and proposed resolutions

| # | Contradiction | Facts | Proposed resolution (no measurement changed, nothing hidden) |
|---|---|---|---|
| B1 | **"Only open-source components" (S2) vs "closed Wi-Fi blob disclosed" (S6, SBOM)** | 9 closed Espressif radio-driver libraries + chip ROM are in the firmware; none is voice-related; the KWS chain (front end, model, runtime, decision) is fully open source; build gate proves no voice SDK | Replace S2 wording with: *"No proprietary voice SDK (checked on every build). The whole keyword pipeline is open source; the only closed code on the chip is Espressif's Wi-Fi/PHY radio driver and boot ROM — disclosed in the SBOM."* Change S6 "the one closed Wi-Fi radio blob" → "the closed Wi-Fi/PHY radio driver". |
| B2 | **Detection → first audio "≈ 2 ms" (S2) vs demo "+6.5…+7.6 ms" (V-A)** | 2.1 ms median without ASR load (E-37); with the ASR server: 6.7–10.6 ms median, p95 15–42 ms, max 57 ms (E-62); the extra time is the server's own receive scheduling while Vosk runs | State the range with conditions: *"First audio reaches the server 2–11 ms (median) after detection; ≤ 22 ms at p95 while the ASR is running."* |
| B3 | **"1.7 ms detection → first packet" (S4) reads as first audio** | 1.7 ms is the stream-start control message, not audio | Replace the tile with the first-audio figure (B2) or relabel it "stream-start message 1.7 ms". |
| B4 | **Keyword end → server "≈ 95 ms" (S2, S4) measured in a different configuration** | 95 / 136 ms from 27 Sep (non-ASR server, keyword-only prompts); with ASR 81 / 172 ms (n = 9, keyword + command); ~84 ms of it is the on-device decision (inference every 60 ms, mean of 3) | Keep 95 / 136 ms with its conditions *("27 Sep, LAN, n = 22")* and add the ASR-in-the-loop result *(81 ms median, 172 ms p95, n = 9)*; or run test T1 below and quote the product-firmware figure. Explain that most of it is the deliberate 3-score confirmation. |
| B5 | **PPT CPU ≤ 9.5 % vs demo lines 10.6–11.4 %** | V-A is the capture build (mic audio over USB for the video): idle 10.9 % on core 1 (n = 822), 11.5 % while streaming; product firmware idle 8.6–9.5 % (V-B shows 8.77 / 8.79 %) | Keep the PPT numbers. In the video, add one spoken/caption line at V-A: *"this build also sends the microphone audio to the PC for the recording, which costs about 2 % CPU; the product firmware at the end idles at 8.8 %"*. Do not remove the lines from the video. |
| B6 | **Measured vs projected** | Projected/unsupported: ₹1 000 hardware, "any ESP32-class", potential uses, "new keyword = same scripts", "never clipped" | Remove or source ₹1 000 (BOM); "any ESP32-class" → "ESP32-S3"; mark uses as potential; "never clipped" → the measured statement in C; keep "power not yet measured". |
| B7 | **False-trigger rate: 15.1 /h (S4) vs 15.8 /h (E-51) vs 13.5 /h (E-39)** | all v2b; 15.1 on 0.86 h, 15.8 on 2.47 h, 13.5 on 2 h (other evening) | Quote **15.8 /h (39 in 2.5 h)** for v2b; use 15.1 → 10.4 /h only for the like-for-like v4 comparison. |
| B8 | **Quiet-night 1 in 5 h shown alone as the accuracy tile (S4)** | E-39 itself forbids quoting it as the general rate | Tile shows both: *"0.2 /h quiet · 15.8 /h with TV/talk"*. |
| B9 | **Privacy "only heard until Hey Vayro" (S5) vs false triggers** | false triggers stream 2–6 s of room audio each | *"Audio leaves the device only after a detection — true or false."* |
| B10 | **"no … licence fee" (S5) vs non-commercial training voices (SBOM)** | 2 of 4 TTS voices are NC | *"No vendor SDK; our code Apache-2.0 (commercial use needs retraining without two non-commercial TTS voices)."* |
| B11 | **"60 entries … with raw data" (S2, S6) vs ledger** | 62 entries; E-08…E-16 are stale plan rows (NOT RUN / FAILING) superseded by E-24, E-35, E-37, E-39, E-42…E-62 | Update E-08…E-16 with "superseded by …" pointers (documentation only) and quote the count after the update. |
| B12 | **Selection "rules declared before each test"** | true, but DEC-26 overrode v4's rule on new evidence | *"Selection rules written before each held-out test; one documented override (new-speaker evidence)."* |
| B13 | **Pre-roll 571 ms (S2, S3) vs 624 ms and arena 40 KiB on screen (V-A)** | demo build = capture build (ring 1.0 s, pre-roll 624 ms, arena 40 KiB); product = 0.75 s / 571 ms / 16 KiB (V-B shows these) | Caption/narration: "demo build"; no PPT change. |
| B14 | **Docs out of date** | `PROJECT_STATE.md` M6 row ("ASR fails… download in progress"), blockers and next-task sections (28 Sep); `DEMO_RUNBOOK.md` describes the superseded dashboard/2:30–3:30 plan | Update both (documentation only). |

---

## C. Approved numbers and wording (single source for PPT, demo narration, idea submission)

Marked ✅ approved (evidence in hand) · 🟡 approved with the stated condition · ⛔ needs confirmation before use.

| Key | Approved value | Approved wording | Evidence | |
|---|---|---|---|---|
| ram_peak | 250 899 B = **245.0 KiB** | "Peak RAM while streaming: 245 KiB — under the 256 KB limit (final firmware; static 139.7 KB + peak heap 111.2 KB)" | E-60 (E-53: 243.8 KiB) | ✅ |
| cpu_idle_both | **4.8–5.5 %** (quote 5.5 % as worst) | "Idle CPU while listening, Wi-Fi connected: 5.5 % averaged over both cores (worst of our runs)" | E-56, E-58, E-60 | ✅ |
| cpu_idle_busiest | **8.6–9.5 %** (quote ≤ 9.5 %) | "Busiest core ≤ 9.5 % (8.6–9.5 % across runs; it rises with Wi-Fi traffic)" | E-43, E-56, E-60, V-B | ✅ |
| cpu_demo_build | 10.9 % idle, 11.5 % streaming | "The demo build also sends the microphone audio to the PC over USB (+~2 % CPU); product firmware idles at 8.8 %" | household run (n = 822), E-61 | ✅ (video narration only) |
| model | 28 024 B, 10 665 params, 212 584 MACs, arena 13 404 B | "28 KB int8 model, 10.7 k parameters, 213 k MACs per inference, 13.4 KB tensor arena" | `metrics.json`, `@KWS` | ✅ |
| cadence | 10 ms frames, 1.02 s window, every 60 ms | "Every 10 ms a 40-band log-mel frame; the model scores the last 1 s every 60 ms" | frontend.json, `@KWS` | ✅ |
| decision | N = 3, 0.80, 2 s | "Detection when the mean of 3 scores ≥ 0.80; 2 s refractory" | sdkconfig.model | ✅ |
| l2_latency | **95 ms median, 136 ms p95** (n = 22) | "Keyword end → audio at the server: 95 ms median, 136 ms p95 (LAN, n = 22); ~84 ms of this is the on-device 3-score confirmation" | E-37 | 🟡 must carry "(27 Sep, LAN, n = 22)"; replace with T1 result if run |
| l2_latency_asr | 81 ms median, 172 ms p95 (n = 9) | "With the ASR running: 81 ms median, 172 ms p95 (n = 9)" | E-62 | 🟡 small n |
| l1_first_audio | 2 ms (no ASR load) – 11 ms median; p95 ≤ 22 ms | "First audio reaches the server 2–11 ms (median) after detection; ≤ 22 ms at p95 with the ASR running" | E-37, E-62 | ✅ |
| streaming | 571 ms pre-roll; 32 kB/s; 0 lost | "Audio is sent only after a detection: from 571 ms before it until the end of speech, 16 kHz 16-bit (32 kB/s); streams arrive complete and bit-exact" | DEC-22, E-44, E-60 | ✅ |
| no_clipping | pre-roll 571 ms vs detection lag ≤ 164 ms | "A command spoken straight after the keyword is inside the stream: it starts 571 ms before the detection, which comes ≤ 164 ms after the keyword ends (measured)" | E-37, E-62 | ✅ |
| recall_s01 | **22/25 (88 %)**, 2/16 confusables | "Speaker 1, held-out session, 0.5–2 m: 22 of 25 keywords" | E-35 | ✅ (label "held-out session") |
| recall_new | **20/25 (80 %)**, 1/16 confusables | "New speaker never used in training: 20 of 25 (0.5 m 10/12, 1 m 6/8, 2 m 4/5)" | E-59 | ✅ (1 session) |
| fa_quiet | 1 in 5 h (0.2 /h) | "Quiet room: 1 false trigger in 5 h (held-out night)" | E-39 | ✅ only together with fa_tv |
| fa_tv | **39 in 2.5 h = 15.8 /h** | "Active household with TV/talk: 15.8 false triggers per hour — our main open issue" | E-51 | ✅ |
| fa_v4 | 15.1 → 10.4 /h (same 52 min) | "Retraining with the device's own false triggers cut this to 10.4 /h (v4) but lowered new-speaker recall to 14/25, so v2b ships" | E-55, E-59 | ✅ |
| asr | publisher WER 36 %; demo 3 of 4 commands exact | "Server ASR: off-the-shelf Vosk en-in (publisher's WER 36 %); in the demo 3 of 4 commands were transcribed exactly" | alphacephei, E-61 | ✅ |
| openness | — | "No proprietary voice SDK (checked on every build). The whole keyword pipeline is open source; the only closed code on the chip is Espressif's Wi-Fi/PHY radio driver and boot ROM, disclosed in the SBOM." | map, gate, SBOM | ✅ |
| licence | Apache-2.0 | "Our code is Apache-2.0. Two of the four TTS voices used for training are non-commercial, so commercial use needs retraining without them." | LICENSE, SBOM | ✅ |
| privacy | — | "Audio leaves the device only after a detection — true or false." | design, E-39, E-51 | ✅ |
| speakers | 2 real speakers; 4 TTS voices | "Tested on 2 real speakers; trained with 4 TTS voices (US, UK, non-native English, Hindi) plus speaker 1" | E-35, E-59, SBOM | ✅ |
| evidence_count | 62 entries | "62 evidence entries" | ledger | 🟡 after the E-08…E-16 update |
| hw_cost | — | — | — | ⛔ needs BOM prices |
| breadboard / photo | — | — | — | ⛔ needs your confirmation / photo |
| platform_scope | ESP32-S3 | "ESP32-S3" (not "any ESP32-class") | tested platform | ✅ |

Machine-readable copy: `docs/submission/approved_numbers.json`.

---

## D. Minimum additional evidence

| # | Item | Why | Effort | Priority |
|---|---|---|---|---|
| T1 | 3-minute keyword-only session on the **product firmware** with the ASR server (10–15 × "Hey Vayro", pause after each) → L2 for the exact final configuration | the headline latency is from 27 Sep's configuration; E-62's n = 9 used keyword + command, where the method is weaker | your 3 min + my 10 min | high (optional if we keep the conditioned wording) |
| T2 | 1–2 phone photos of the board + microphone setup | "working prototype" is only shown as console text; confirms/denies "breadboard" | your 2 min | high |
| T3 | BOM with the prices you actually paid | supports or removes "≈ ₹1 000" | your 5 min | medium |
| T4 | Ledger E-08…E-16 → "superseded by …"; `PROJECT_STATE.md` and `DEMO_RUNBOOK.md` refresh | removes stale "NOT RUN / FAILING" rows | me, 15 min, no tests | medium |
| T5 | (optional) ≥ 10 min idle CPU on the exact final binary | E-60 idle part was 3 min; E-56 (12 min) was the same source, different build hash | 12 min, board only | low |
