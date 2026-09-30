# Evidence

Raw logs and results of every build, run and test. [`docs/EVIDENCE_LEDGER.md`](../docs/EVIDENCE_LEDGER.md) is the index:
each entry (E-01 … E-63) states a claim, how it was measured, the value, its limits, and the files here that back it.

## Layout

| Folder / file | Contents |
|---|---|
| `runs/<date>_<time>_<label>/` | one device session recorded over USB by `host/capture.py`: `device_log.txt` (every telemetry line), `device_events.jsonl` (the same lines parsed), `capture_summary.json` (integrity accounting, script segments, triggers), `posteriors_device.bin` (the model's score for every inference), analysis outputs |
| `server/<date>_<time>/` | one ASR-server session: `activations.csv`, one JSON per stream (timestamps, latency fields, transcript), `latency_report.json`, `stream_integrity*.json` |
| `t1/`, `prompts/` | the final latency test (T1) and the wall-clock logs of on-screen prompts |
| `m0/`, `m1/`, `m2/`, `*.log`, `*.txt` | build, size and flash logs of the milestones and of the memory (EXP-1) and CPU (EXP-2) experiments |
| `m6_replay/`, `m6_asr_control/` | server-side ASR experiments replayed from recorded sessions |
| `demo/` | metadata of the demonstration takes |

Binary record formats: `posteriors_device.bin` is a sequence of 6-byte records `{u32 frame, i8 raw output, u8 trigger}`;
a frame is 10 ms and the probability is `(raw + 128) / 256`.

## What is not published

This repository is the public copy of a development repository. The following are kept private and are absent from
every commit here:

| Withheld | Why |
|---|---|
| all audio and video (`*.wav`, `*.mp4`): recorded sessions, server-side streams, the demonstration video | they contain the voices of the speakers and household sound (family conversation, television, singing) |
| `features_device.bin` files | log-mel features derived from that audio; the largest is 309 MB |
| the official SIH presentation template | a third-party file |
| internal planning notes | not part of the engineering record |

Consequences for anyone reproducing results from this copy:

- Everything computed from **logs, JSON results and score files** can be re-run: memory (S4), CPU, latency, stream
  accounting, false-trigger counts per hour, the comparison of live triggers, and six of the seven charts in
  `docs/report/make_figures.py`.
- Anything that needs the **audio itself** cannot: re-running feature parity, replaying a model on a recording, the
  stream bit-exactness check, retraining on the project's own recordings, and the microphone spectrum chart. Their
  recorded outputs (`parity_report.json`, `posterior_parity.json`, `stream_integrity.json`, `eval_*.json`) are here.

## Redactions

In text files, three kinds of identifier were replaced, in every commit:

- the home Wi-Fi network name → `home-wifi-redacted`
- hardware (MAC) addresses → vendor prefix kept, last three bytes replaced (`e0:72:a1:xx:xx:xx`)
- the Windows account name inside absolute paths → `user`

One more kind of content is withheld inside otherwise published files: the **recognised text of streams that captured
ambient household sound** (television, family conversation picked up by a false trigger or by a synthetic test
stream). In the server logs, and in the activation JSON and CSV files of those streams, the text fields read
`[withheld: ambient audio]` and the word list is empty. Transcripts of the scripted test sessions, where the speaker
read prompts (E-48, E-49, E-61, E-63), are published unchanged, as are all timing, size and integrity fields.

No measurement, timestamp or result was changed. Private-range IP addresses (`192.168.x.x`) are left as recorded.

## History

The public history is produced from the development history by [`tools/publish_public.py`](../tools/publish_public.py):
same commits, order, dates and messages, with the withheld paths removed, the redactions applied and the commit e-mail
replaced by a GitHub no-reply address. The tool scans the result and refuses to finish if anything withheld or
unredacted is still reachable.

Commit ids change in that process. Ids quoted inside the evidence (for example the commits in which a model-selection
rule was declared before its test) are ids of the development history. Every public commit ends with
`Original-commit: <development id>`, so:

```bash
git log --grep 3ffc188        # the public commit that corresponds to development commit 3ffc188
```
