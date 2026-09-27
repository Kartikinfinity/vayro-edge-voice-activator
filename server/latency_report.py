"""Latency report for one ingest session (architecture §10.2), from server/ingest.py outputs.

Per activation:
  L1_start / L1_audio0  [MEAS]  server receive time - device detect time (via NTP-style offset; ± half the RTT)
  lag_audio_ms          [MEAS]  (trigger position in the stream) - (keyword acoustic end located in the SAME
                                streamed audio). The stream starts preroll_ms before the trigger, so the
                                keyword tail is inside it. Speech-band energy, local floor + 9 dB.
  capture_delta_ms      [EST]   time from the last ring sample's capture to the trigger decision
                                (DMA hop <= 10 ms + front end + inference ~2-3 ms; 1.08 ms mic group delay):
                                taken as 10 ms +/- 7 ms, NOT measured (IN-1/IN-2 GPIO capture would measure it).
  L2_est_ms = L1_audio0 + lag_audio_ms + capture_delta_ms   (keyword acoustic end -> first audio at the server)

Usage: python server/latency_report.py evidence/server/<session>
"""
import json
import pathlib
import sys
import wave

import numpy as np
from scipy import signal

FS = 16000
SOS = signal.butter(4, [300, 4000], btype="band", fs=FS, output="sos")
CAPTURE_DELTA_MS, CAPTURE_DELTA_UNC_MS = 10.0, 7.0


def kw_end_in_stream(pcm, trig_off, fr=320):
    y = signal.sosfilt(SOS, pcm.astype(np.float64))
    n = len(y) // fr
    e = 20 * np.log10(np.sqrt(np.mean(y[: n * fr].reshape(n, fr) ** 2, axis=1)) + 1e-9)
    e = signal.medfilt(e, 5)
    act = e > np.percentile(e, 20) + 9
    last = trig_off // fr  # the keyword must have ended before the trigger fired
    idx = [i for i in range(min(last + 1, n)) if act[i]]
    if not idx:
        return None
    end = idx[-1]
    return (end + 1) * fr  # sample offset of the acoustic end (20 ms resolution)


def main(sess):
    rows = []
    for j in sorted(sess.glob("act*.json")):
        a = json.loads(j.read_text(encoding="utf-8"))
        with wave.open(str(j.with_suffix(".wav"))) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        trig_off = a["preroll_ms"] * 16
        ke = kw_end_in_stream(pcm, trig_off)
        r = {"activation": a["activation"], "L1_start_ms": a.get("L1_start_ms"), "L1_audio0_ms": a.get("L1_audio0_ms"),
             "clock_unc_ms": a.get("clock_uncertainty_ms_half_rtt"), "audio_s": a["audio_seconds"],
             "end_reason": a["device_end_reason"], "overrun": a["overrun"], "seq_gaps": a["seq_gaps"],
             "min_slack_ms": a["device_min_slack_ms"]}
        if ke is not None and a.get("L1_audio0_ms") is not None:
            r["lag_audio_ms"] = round((trig_off - ke) / 16, 1)
            r["L2_est_ms"] = round(a["L1_audio0_ms"] + r["lag_audio_ms"] + CAPTURE_DELTA_MS, 1)
        rows.append(r)

    def stats(k):
        v = np.array([r[k] for r in rows if r.get(k) is not None], float)
        return {"n": int(len(v)), "mean": round(float(v.mean()), 2), "p50": round(float(np.median(v)), 2),
                "p95": round(float(np.percentile(v, 95)), 2), "max": round(float(v.max()), 2)} if len(v) else None

    rep = {"session": sess.name, "activations": rows,
           "summary": {k: stats(k) for k in ("L1_start_ms", "L1_audio0_ms", "lag_audio_ms", "L2_est_ms", "clock_unc_ms")},
           "definitions": {"capture_delta_ms": f"[EST] {CAPTURE_DELTA_MS} +/- {CAPTURE_DELTA_UNC_MS} ms, not measured",
                           "L2_est": "L1_audio0 + lag_audio + capture_delta; keyword end located at 20 ms resolution"}}
    (sess / "latency_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    for r in rows:
        print(r)
    print(json.dumps(rep["summary"], indent=2))


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
