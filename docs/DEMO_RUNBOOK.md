# Demo video runbook (PS26172, final firmware: v2b @ 0.80 (DEC-26), product configuration DEC-22 + DEC-24)

One continuous take, no cuts inside a step, no edited numbers. Target length 2:30–3:30. Record the screen (Win + Alt + R
or OBS) and, if possible, a phone camera on the board at the same time.

## 0. Before recording (5 min)

0. **PC awake (disable sleep), ASR server running** — a sleeping PC killed the server once (E-58).
1. PC on the same Wi-Fi/LAN as the board, IP **192.168.1.13** (the server address is built into the firmware, E-41).
   Check: `ipconfig` shows `IPv4 Address . . . : 192.168.1.13`. Disable PC sleep for the session.
2. Board on USB (COM7), mic ~30–50 cm from the speaker. TV off for the main part.
3. Open two terminal windows side by side, font size ≥ 16.

**Window A — ASR server** (wait for `ingest listening`, ~30 s model load; only one server can hold port 5005 — if it fails to start, another server is still running):
```
D:/ps26172/.venv-host/Scripts/python.exe -u D:/ps26172/server/ingest.py --port 5005 --asr D:/ps26172_ext/vosk/vosk-model-en-in-0.5 --min-after-s 0.8 --stream-s-max 6
```
**Window B — device console** (resets the board; shows boot, memory, keyword and CPU lines):
```
D:/ps26172/.venv-host/Scripts/python.exe D:/ps26172/host/capture.py --port COM7 --wall-s 900 --label demo_video --note "demo video take"
```

## 1. Hardware (≈ 20 s, camera)
Show the ESP32-S3 N16R8 + INMP441 wiring (SCK→GPIO6, WS→GPIO5, SD→GPIO4, L/R→GND). Say: "Everything you hear from now
on is processed on this microcontroller; only after the keyword does audio leave the device."

## 2. Boot (≈ 20 s, Window B)
Point at: `@BOOT` (ESP-IDF 5.5.5, PSRAM disabled), `@KWS … run=v2b … model_bytes=28024 arena_used=13404`,
`@MEM … streaming …`, `@NET wifi=up`, `@NET tcp=connected`, and in Window A `device connected`.

## 3. Keyword + command, 5 times (≈ 90 s)
Say each once, normal voice, then wait for the transcript in Window A before the next:
1. "Hey Vayro … turn on the light"
2. "Hey Vayro … what time is it"
3. "Hey Vayro … play some music"
4. "Hey Vayro … open the door"
5. "Hey Vayro … set a timer for five minutes"

For each, point at: Window B `@KW … p=… avg=…` and `@STREAM … audio0_tx_us`; Window A
`activation N: … L1_start … ms, L1_audio0 … ms … seq_gaps=0` and `ASR: "…"`.
**If a keyword is missed or a transcript is wrong, keep it in the video** and say so — the numbers in the PPT are the
measured ones, not the demo's.

## 4. No keyword → no activation (≈ 20 s)
Talk normally for ~15 s without the keyword (e.g. read a sentence aloud). Show that nothing appears in Window A.

## 5. Efficiency on screen (≈ 20 s)
Wait for an `@CPU` line in Window B (every 10 s): `core1_busy` ≈ 9 %, `core0_busy` ≈ 1 %. Point at `@MEM … int_min_free`.
Say the measured figures from the evidence: peak RAM while streaming 245.0 KiB and idle CPU 5.5 % mean of both cores,
busiest core ≤ 9.5 % (E-60).

## 6. Close (≈ 10 s)
Ctrl+C in Window B (it prints `Saved run`), then Ctrl+C in Window A. The run folder `evidence/runs/*_demo_video` and the
server folder are the raw record of the take — keep them with the video.
