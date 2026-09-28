"""Replay a USB-capture run through the REAL server code path (ingest.Session): the device's own @KW trigger times from
the run, its pre-roll, 40 ms CONT packets cut from the captured int16 stream, and the device busy policy (a trigger
while a stream is open is not streamed; after END the device drains one more packet). Transcripts, endpoints and
WAV/JSON files come out exactly as the live server would write them, so server changes can be checked on recorded
sessions before a live run. Latency fields are not meaningful here (no clock offset).

Usage (host venv): python server/replay_session.py <run_dir> <vosk_model_dir> <out_dir>
                   [--endpoint vad|asr] [--grammar FILE] [--min-after-s 0.8] [--stream-s-max 6]"""
import argparse
import json
import pathlib
import struct
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ingest  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("model")
ap.add_argument("out")
ap.add_argument("--endpoint", choices=["vad", "asr"], default="vad")
ap.add_argument("--grammar", default="")
ap.add_argument("--min-after-s", type=float, default=0.8)
ap.add_argument("--stream-s-max", type=float, default=6.0)
ap.add_argument("--stream-s", type=float, default=3.0)
ap.add_argument("--preroll-ms", type=int, default=624)
args = ap.parse_args()

from vosk import Model, SetLogLevel  # noqa: E402

SetLogLevel(-1)
ingest.ASR_MODEL = Model(args.model)
ingest.ASR_GRAMMAR = pathlib.Path(args.grammar).read_text(encoding="utf-8") if args.grammar else None
run = pathlib.Path(args.run)
out = pathlib.Path(args.out)
out.mkdir(parents=True, exist_ok=True)
with wave.open(str(run / "audio_16bit.wav")) as w:
    pcm = w.readframes(w.getnframes())
trig = json.loads((run / "capture_summary.json").read_text(encoding="utf-8"))["device_kw_triggers"]


class NullConn:
    def sendall(self, b):
        pass


s = ingest.Session(NullConn(), out, args)
s.conn_stamp = "replay"
busy_until, act, rows = -1.0, 0, []
for k in trig:
    t = k["t_ms"] / 1000
    if t < busy_until:
        rows.append({"t": t, "streamed": False})
        continue
    act += 1
    first = int(round((t - args.preroll_ms / 1000) * 16000))
    s.on_packet(ingest.F_START, 0, struct.pack("<IIQIIb", act, k["frame"], int(t * 1e6), args.preroll_ms, first,
                                                k["raw"]).ljust(32, b"\0"), 0)
    i, seq, drain = first * 2, 0, None
    while i + 1280 <= len(pcm):
        seq += 1
        s.on_packet(ingest.F_CONT, seq, pcm[i:i + 1280], 0)
        i += 1280
        if drain is None and s.act["end_sent"]:
            drain = 1
        elif drain is not None:
            drain -= 1
            if drain < 0:
                break
    sent = i // 2 - first
    a = s.act
    s.on_packet(ingest.F_END, 0, struct.pack("<IIII", act, sent, 0, 1), 0)
    busy_until = (i // 2) / 16000
    j = json.loads((out / f"replay_act{act:04d}.json").read_text(encoding="utf-8"))
    rows.append({"t": t, "streamed": True, "act": act, "endpoint_s": j["asr_endpoint_at_s"],
                 "endpoint_by": j.get("endpoint_by"), "after_trigger": j["asr_after_trigger"],
                 "transcript": j["asr_transcript"]})
for r in rows:
    if r["streamed"]:
        print(f"KW@{r['t']:7.2f}  act {r['act']}  END {r['endpoint_s']} s by {r['endpoint_by']:<22s} "
              f"after-trigger: \"{r['after_trigger']}\"")
    else:
        print(f"KW@{r['t']:7.2f}  NOT STREAMED (stream open)")
(out / "replay_summary.json").write_text(json.dumps({"run": run.name, "model": args.model, "endpoint": args.endpoint,
                                                     "grammar": args.grammar, "rows": rows}, indent=2),
                                         encoding="utf-8")
