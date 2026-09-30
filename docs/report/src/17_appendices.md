# Source and Evidence Index {#app-sources .appendix}

## Documents

Table: Primary documents {#tab-docs}
| Document | Location | Role |
|---|---|---|
| Problem statement | `D:\sih final\sih 2026  (1).pdf` | the only binding source |
| Architecture study (Track C) | `D:\sih final\PS26172_TRACK_C_HARDWARE_ARCHITECTURE.md` | research basis (Chapter 2) |
| Project state record | `docs/PROJECT_STATE.md` | requirements R1–R10, decisions DEC-01…26, conflicts C-01…12, milestones |
| Evidence ledger | `docs/EVIDENCE_LEDGER.md` | E-01…E-63 with raw-file paths |
| SBOM | `docs/SBOM.md` | components, versions, licences, disclosures |
| M1 experiment plan | `docs/experiments/M1_audio_path.md` | M1 hypotheses and protocol |
| Consistency sheet | `docs/submission/EVIDENCE_CONSISTENCY_SHEET.md`, `approved_numbers.json` | audit of claims (30 Sep) |
| Selection rules and outcomes | `model/artifacts/selection_rule_v2/v3/v4.json`, `selection_v*_outcome.json`, `selection_final.json` | model choice history |
| Report figure data | `docs/report/figures/figure_data_summary.json` | values computed by `make_figures.py` for this report |

## Evidence ledger index

Table: Ledger entries and where their raw data is (paths under `evidence/` unless stated) {#tab-ledger}
| ID | What it establishes | Raw data |
|---|---|---|
| E-01 | pinned build, forbidden-dependency gate PASS | `m0/size_uart_m1build.txt` |
| E-02 | live 24-bit 16 kHz audio through I2S0 | `runs/20260926_214931_m1_msb_settle_warm` |
| E-03 | pass-band edge visible at 6 768 Hz | same |
| E-04 | no zero-output start-up; 0.56 ms to first sample | `runs/20260926_221709_m1_sessionA_cold` |
| E-05 | mono mode halves DMA traffic | `@DIAG` lines, M1 runs |
| E-06 | speech vs room levels; int16 shift decision | `runs/20260926_221709_m1_sessionA_cold` |
| E-07 | capture integrity (short runs) | `runs/20260927_125547_m1_link_fix_60s_b` |
| E-08…E-16 | early plan rows, superseded or verified on 30 Sep (see E-14, E-15) | pointers in the ledger |
| E-14 | trained from random initialisation (code review) | `model/train/train.py` |
| E-15 | no voice SDK; closed Wi-Fi/PHY libraries listed | `final_product_build_v2b.log`, link map |
| E-17 | static RAM of the M1 build (IRAM code 60 015 B) | `m0/size_uart_m1build.txt` |
| E-18 | Philips one bit late; MSB aligned | `runs/20260926_214456_m1_align_sweep_warm` |
| E-19 | start-up DC transient; in-band settling < 100 ms | M1 runs |
| E-20 | capture-link faults found and fixed | several M1 runs |
| E-21 | feature parity: fail 5 995/5 998 → pass 12 000/12 000 | `runs/20260927_134200…`, `…145754…`, `…150156…` |
| E-22 | model output parity 1 984/1 984 | `runs/20260927_145754_m2m3_parity_canonical_120s` |
| E-23 | per-stage CPU cycles (capture build) | same, `posterior_parity.json` |
| E-24 | model footprint | `@KWS`, `model/artifacts/v0/metrics.json` |
| E-25 | v0 offline on S01 session 1 | `model/artifacts/v0/eval_test_S01.json` |
| E-26 | live triggers = offline replay (27/27) | `runs/20260927_151127_kw_S01_s2/device_trigger_eval.json` |
| E-27 | v0 live on S01 session 2 | `model/artifacts/v0/eval_v0_val_s2.json` |
| E-28, E-31 | 0 FA in 401 s daytime held-out (v0, v2b) | `…/eval_*heldout_c002.json` |
| E-29 | static RAM of the network capture build | `m5_size_netcheck.txt` |
| E-30 | v2b validation result and selection | `model/artifacts/v2b/eval_val_s2.json` |
| E-32 | Wi-Fi + warm TCP bring-up | `runs/20260927_192653_m5_net_bringup` |
| E-33 | corrected: 150 s session without a keyword | `runs/20260927_192738_m5_live_kw` |
| E-34 | Wi-Fi interference hypothesis rejected (A/B) | `runs/20260927_193239_ab_wifi_OFF`, `…193322_ab_wifi_ON` |
| E-35 | **S01 session 3: 22/25, 2/16** | `runs/20260927_195253_kw_S01_s3`, `model/artifacts/v2b/eval_test_S01_s3.json` |
| E-36 | 24/24 streams with pre-roll, 0 overruns | `server/20260927_192112/` |
| E-37 | first latency (95 / 136 ms) | `server/20260927_192112/latency_report.json` |
| E-38 | 10 unattended detections, audio lost (unresolved) | `server/20260927_192112/activations.csv` |
| E-39 | overnight false activations by activity | `runs/20260927_203133_ambient_night_20260927` |
| E-40 | 10 h capture integrity | same, `capture_summary.json` |
| E-41 | network outage behaviour | same, `device_log.txt` |
| E-42 | EXP-1 product, not streaming (238.1 KiB) | `exp1_product_build_v2.log`, `runs/20260928_075330…` |
| E-43 | EXP-2 first CPU | `runs/20260928_080133_exp2_cpu_selftest` |
| E-44 | 23/23 streams bit-exact | `server/20260927_192112/stream_integrity.json` |
| E-45 | first ASR session (corrected) + level control | `server/20260928_175052/`, `m6_asr_control/` |
| E-46 | 190 ms L1 artefact diagnosed | `server/20260928_175052/activations.csv` |
| E-47 | false activation from devotional singing | `server/20260928_175052/c175129_act0005.wav` |
| E-48 | M6 command test, small ASR: 1/4 | `runs/20260928_192727_m6_cmd_S01` |
| E-49 | M6 v2 with en-in-0.5 + VAD: 2/10 end to end | `server/20260928_201836/` |
| E-50 | capture stalls under host load | `household_eve.stdout.log` |
| E-51 | **household FA: v2b 15.8 /h, v3 19.9 /h** | `model/artifacts/household_compare_20260928.json` |
| E-52 | streaming peak 259 255 B | `exp1_streaming_size.log`, `runs/20260928_222620…` |
| E-53 | after DEC-24: 249 615 B | `exp1_streaming_size_dec24.log`, `runs/20260928_225547…` |
| E-54 | v4 built | `model/artifacts/v4/` |
| E-55 | v4 selection rules a–c | `model/artifacts/selection_v4_outcome.json` |
| E-56 | EXP-2, 12 minutes | `runs/20260928_230150_exp2_cpu_idle_12min_dec24` |
| E-57 | v4 rule (d): 10/10 vs 10/10 | `model/artifacts/prompt_hits_20260929_192230_m6_v3_S01.json` |
| E-58 | final v4 firmware; 3/31 overruns → AsrJob | `runs/20260929_194642_final_v4_streaming`, `server_m6f.stdout.log` |
| E-59 | **new speaker: v4 14/25, v2b 20/25** | `runs/20260929_201213_kw_S02_s1`, `model/artifacts/*/eval_newspk_S02_s1.json` |
| E-60 | **final firmware: 245.0 KiB, 30/30, idle CPU** | `runs/20260929_202327_final_v2b_confirm`, `final_product_size_v2b.log` |
| E-61 | demonstration run | `demo/PS26172_demo_90s/cut_meta.json` |
| E-62 | latency with ASR in the loop | `server/20260929_{214632,221342,195557}/latency_report.json` |
| E-63 | **T1: 12/12, L2 138 / 196 ms** | `t1/20260930_085535/`, `server/20260930_085548/latency_report.json` |

## Decisions index

Table: Implementation decisions (from `docs/PROJECT_STATE.md` §4) {#tab-decs}
| ID | Decision |
|---|---|
| DEC-01 | ESP-IDF v5.5.5 native, not PlatformIO |
| DEC-02 | repository at `D:\ps26172` (no spaces in the path) |
| DEC-03 | CRC-framed USB serial as the M1 debug/data link |
| DEC-04 | capture keeps the full 24-bit sample; host derives int16 identically |
| DEC-05 | unified ring built at M2 |
| DEC-06 | **I2S framing = MSB-justified** (measured) |
| DEC-07 | native USB-Serial-JTAG console; firmware waits for the host start byte |
| DEC-08 | keyword "Hey Vayro" |
| DEC-09 | int16 = bits 23:8 kept |
| DEC-10 | MIC_SETTLE 300 ms kept |
| DEC-11 | **windowed DS-CNN every 60 ms instead of a streaming model** (user-approved) |
| DEC-12 | training environment: WSL Ubuntu, uv, CPython 3.12, TensorFlow CPU, Piper, LibriSpeech |
| DEC-13 | ambient recording afternoon + overnight through this microphone |
| DEC-14 | TTS spellings "Hey Vyro" / "हे वाइरो" |
| DEC-15 | microfrontend vendored unmodified; all parameters from `frontend.json` |
| DEC-16 | **canonical front-end tables copied from the host twin** |
| DEC-17 | static batch-1 export (5 operator types) |
| DEC-18 | selection needs a real validation set separate from the test set |
| DEC-19 | v2 split: S01 s1 train, s2 validation, later sessions test |
| DEC-20 | recording protocol v2 and prompt scoring |
| DEC-21 | transport as specified: warm TCP, 8-byte header, 571/624 ms pre-roll, clock pings; modem sleep off |
| DEC-22 | **product configuration** (memory trims, 0.75 s ring, 571 ms pre-roll, IRAM → flash) |
| DEC-23 | v3 not shipped (household FA worse) |
| DEC-24 | **further product trims** (heap poisoning, A-MPDU, TX buffers, IPv6) |
| DEC-25 | v4 trained with a rule declared first |
| DEC-26 | **ship v2b @ 0.80, overriding v4's rule** (new-speaker evidence) |

# Discrepancies Found During This Reconstruction {#app-discrepancies .appendix}

Cross-checking the records against the code and raw data found the following. None changes a headline number; they are listed so that no reader is misled by an out-of-date file. (The larger set of presentation-wording contradictions audited on 30 Sep, B1–B14, is in the consistency sheet and was resolved there.)

Table: Discrepancies and stale records {#tab-discrep}
| # | Where | What it says | What the evidence shows | Verdict |
|---|---|---|---|---|
| 1 | `PROJECT_STATE.md` header | "Last updated 2026-09-26 ~21:00" | the file contains 30 Sep content | stale header |
| 2 | `PROJECT_STATE.md` §8, M3 row | "v3 @ 0.60 is the candidate; ship decision pending (DEC-23)" | DEC-23 resolved 28 Sep; DEC-26 ships v2b | stale row |
| 3 | `PROJECT_STATE.md` §8, M4 row | "logic analyser arrives 28 Sep" | no analyser was ever used (C-06) | stale |
| 4 | `PROJECT_STATE.md` §5, C-11 | proposes a 2–3 s MIC_SETTLE | withdrawn by DEC-10 | stale row |
| 5 | `docs/experiments/M1_audio_path.md` | "Results: NOT RUN" | M1 was run and is in E-02…E-07, E-18…E-20 | never updated |
| 6 | `Kconfig.projbuild` help, `sdkconfig.product` comment | the capture TX pool "shrinks to 4 slots" | `app_main.c`: `POOL_N 1` when capture streams are off | comment inaccurate |
| 7 | `sdkconfig.defaults` comment | "Wi-Fi / lwIP trims are added at M5" | they live in `sdkconfig.product` | comment stale |
| 8 | `SBOM.md` header | "Status 28 Sep" | content updated 29 Sep (v2b, Apache-2.0) | stale date |
| 9 | Ledger E-60 | idle CPU only | the same run's streaming phase: core 1 10.51 % mean, 10.83 % max (this report, [[fig-cpu]]) | **new finding**, not a contradiction |
| 10 | Ledger E-56 | core 1 p99 8.97 % | recomputed p99 8.94 % (nearest-rank); mean and max identical | percentile-method difference only |
| 11 | `DEMO_RUNBOOK.md` | "ASR model load ~30 s" | 11.7 s in the T1 run | condition-dependent |
| 12 | Architecture study §B5 | pins BCK 4 / WS 5 / SD 6 | wired BCK 6 / WS 5 / SD 4 (C-05) | documented deviation |
| 13 | Architecture study §3.5 | S4 ≈ 227 KiB | 245.0 KiB measured; IRAM code missing from the estimate (C-10) | estimate vs measurement |

# Completeness Audit {#app-audit .appendix}

Table: The report's quality-control checklist, with the result of each check {#tab-audit}
| Check | Result |
|---|---|
| The original research document has been examined | **Yes** — the Track C study was read in full; the PS text read in full. The documents it cites (Master Spec, Tracks A/B, datasheets) were not available and are marked as such. |
| The actual project requirements are documented | **Yes** — R1–R10 from the PS, with interpretations (Chapter 3). |
| The actual hardware inventory is complete | **Yes, with gaps** — chip identity measured; board maker/model, breadboard, pull-down and decoupling not recorded (Chapter 4). |
| Important component specifications are accurate | **Yes** — measured values where they exist; datasheet values quoted via the study and labelled [DOCUMENTED]. |
| Relevant wiring and interfaces are documented | **Yes** — from `sdkconfig.board`, confirmed by measurement. |
| Software tools and confirmed versions are included | **Yes** — from lock files, logs and build caches; four versions could not be confirmed and are listed. |
| The actual architecture is explained | **Yes** (Chapter 6). |
| Repository structure and important source files are documented | **Yes** (Chapter 7). |
| Important code paths are explained | **Yes** — boot, reader task, decision, ring, front end, KWS engine, streamer, server. |
| Relevant algorithms and processing stages are documented | **Yes** (Chapter 8). |
| Hardware-software integration is explained | **Yes** (Chapter 9). |
| Deployment and flashing details are documented where evidence exists | **Yes** — the final flash is evidenced by the firmware's own ELF hash, not by a flash log (stated). |
| The chronological development process is reconstructed | **Yes** (Chapter 10, [[fig-phases]]). |
| Important experiments and tests are documented | **Yes** — 33 tests, including failures and corrections. |
| Failed tests and debugging iterations are included | **Yes** (Chapters 10–11). |
| Final results are separated from projections | **Yes** — study estimates appear only in comparison tables, labelled as estimates. |
| The actual innovations are analysed in depth | **Yes** (Chapter 13), with ordinary choices listed separately and credit to the study stated. |
| Remaining limitations and unverified claims are identified | **Yes** (Chapters 12, 14; [UNVERIFIED] labels). |
| Every important factual statement has an identifiable source | **Yes, where possible** — file paths and ledger IDs throughout. |
| No unrelated material is included | **Yes** — presentation and video content excluded. |
| No PPT or demo-video content is reproduced as a deliverable | **Yes.** |
| The report accurately describes the final implemented state | **Yes** — final configuration identified by model SHA-256, firmware ELF hashes and configuration files. |

**Limits of this reconstruction.** Results labelled [DOCUMENTED] were taken from the ledger without re-running their analysis; all headline numbers were re-computed. The reconstruction could not observe the physical set-up, so everything about the room, distances and the board's construction rests on the records.

# Command Reference {#app-commands .appendix}

```powershell
# Build and flash the final product firmware (from any directory; COM7 = the board's native USB)
powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console usbjtag -Port COM7 `
    -ExtraDefaults D:\ps26172\firmware\sdkconfig.product -BuildTag product build flash

# Regenerate the model source + operating point from a trained model folder
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\tools\gen_model_source.py model\artifacts\v2b

# Start the ASR server (final configuration)
D:\ps26172\.venv-host\Scripts\python.exe -u D:\ps26172\server\ingest.py --port 5005 `
    --asr D:\ps26172_ext\vosk\vosk-model-en-in-0.5 --min-after-s 0.8 --stream-s-max 6

# Device console / evidence recording (resets the board, writes evidence\runs\<time>_<label>\)
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\host\capture.py --port COM7 --wall-s 600 --label my_run

# Scripted keyword session (prompts on screen, audio + features + scores recorded)
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\host\capture.py --port COM7 `
    --script-file host\scripts\kw_session_v2.txt --label kw_S03_s1

# Latency report and stream integrity for a server session
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\server\latency_report.py evidence\server\<session>
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\server\stream_integrity.py evidence\runs\<capture run> evidence\server\<session>

# T1 latency test (starts the server and console, shows 12 prompts)
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\host\t1_session.py
```

```bash
# In WSL (training environment ~/.venvs/ps26172)
python model/frontend/parity_test.py /mnt/d/ps26172/evidence/runs/<run>        # device vs host features
python model/eval/eval_stream.py --model model/artifacts/v2b/model_int8.tflite \
       --runs /mnt/d/ps26172/evidence/runs/<run> --tag my_test                   # device-identical replay
bash model/train/run_v4.sh                                                       # full dataset + train + export (v4 recipe)
```

```powershell
# Rebuild this report (figures from evidence, then HTML + PDF)
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\docs\report\make_figures.py
D:\ps26172\.venv-host\Scripts\python.exe D:\ps26172\docs\report\build_report.py
```
