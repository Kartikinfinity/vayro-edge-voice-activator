"""Evaluate an int8 TFLite model on continuous device recordings, mirroring the device decision logic.

Per run: twin features over the whole stream (reset at start, as after boot) -> inference every
STRIDE frames on the last WIN frames -> mean of last N posteriors -> threshold -> 2 s refractory.
Keyword runs (capture.py --script-file): recall per condition + detection lag vs the keyword's
acoustic end (energy-located in each prompt window). All runs: false activations with exposure.

Usage (WSL venv):
  python model/eval/eval_stream.py --model model/artifacts/v0/model_int8.tflite --runs <run_dir> [<run_dir> ...]
         [--thresholds 0.5,0.7,...] [--n 1,3,5] --tag test_S01
"""
import argparse
import json
import pathlib
import sys
import wave

import numpy as np
import tensorflow as tf
from scipy import signal

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.frontend.psfe import Frontend  # noqa: E402

FS, HOP, FE_WIN, WIN, STRIDE, REFRACTORY_S = 16000, 160, 480, 100, 6, 2.0
SOS = signal.butter(4, [125, 6500], btype="band", fs=FS, output="sos")


def load_run_audio(run):
    files = sorted(run.glob("audio_16bit_c*.wav")) or [run / "audio_16bit.wav"]
    parts = []
    for f in files:
        with wave.open(str(f)) as w:
            parts.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16))
    return np.concatenate(parts)


def posteriors(model_path, feats_i8):
    # Reference kernels: closest host analogue of TFLM's integer kernels (XNNPACK may round differently).
    it = tf.lite.Interpreter(model_path=str(model_path),
                             experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
    ind, outd = it.get_input_details()[0], it.get_output_details()[0]
    (isc, izp), (osc, ozp) = ind["quantization"], outd["quantization"]
    lut = np.clip(np.round(np.arange(-128, 128) / 128.0 / isc + izp), -128, 127).astype(np.int8)  # device LUT
    ends = np.arange(WIN - 1, len(feats_i8), STRIDE)
    it.allocate_tensors()  # static batch-1 device graph: one window per invoke, exactly as on the device
    raw = np.empty(len(ends), np.int8)
    x = np.zeros((1, WIN, 1, feats_i8.shape[1]), np.int8)
    for j, ee in enumerate(ends):
        x[0, :, 0, :] = lut[feats_i8[ee - WIN + 1:ee + 1].astype(np.int16) + 128]
        it.set_tensor(ind["index"], x)
        it.invoke()
        raw[j] = it.get_tensor(outd["index"])[0, 0]
    p = (raw.astype(np.float32) - ozp) * osc
    t_end = (FE_WIN + HOP * ends) / FS  # time (s) of the last sample in each window
    return t_end, p, ends, raw


def detect(t, p, thr, n):
    sm = np.convolve(p, np.ones(n) / n, mode="full")[:len(p)]
    dets, last = [], -1e9
    for ti, si in zip(t, sm):
        if si >= thr and ti - last >= REFRACTORY_S:
            dets.append(float(ti))
            last = ti
    return dets


SOS_SPEECH = signal.butter(4, [300, 4000], btype="band", fs=FS, output="sos")


def keyword_ends(run, audio, fr=320, rel_db=9.0, bridge_s=0.3, max_span_s=2.0):
    """Locate the utterance in each kw_* prompt window (v2, robust):
    speech-band (300-4000 Hz) 20 ms energy, 5-frame median smoothing; threshold = the window's own 20th
    percentile + rel_db; keep the burst containing the energy peak, bridging gaps <= bridge_s (the pause in
    "Hey ... Vayro"), capped at max_span_s around the peak. v1 used a global floor + 10 dB on 125-6500 Hz
    and produced impossible spans (0.02 s, 2.7 s) under fan noise — see model/artifacts/*/kw_durations."""
    summ = json.loads((run / "capture_summary.json").read_text(encoding="utf-8"))
    segs = summ.get("script_segments", [])
    y = signal.sosfilt(SOS_SPEECH, audio.astype(np.float64))
    kws, skipped = [], []
    for g in segs:
        if not g["name"].startswith("kw_"):
            continue
        a = g["t0_s"]
        s = y[int(a * FS):int((g["t1_s"] + 0.3) * FS)]
        n = len(s) // fr
        e = 20 * np.log10(np.sqrt(np.mean(s[: n * fr].reshape(n, fr) ** 2, axis=1)) + 1e-9)
        e = signal.medfilt(e, 5)
        thr = np.percentile(e, 20) + rel_db
        act = e > thr
        pk = int(np.argmax(e))
        if not act[pk]:
            skipped.append(g["name"])
            continue
        gap = int(bridge_s * FS / fr)
        lo = hi = pk
        while lo > 0 and np.any(act[max(0, lo - gap):lo]):
            lo = max(0, lo - gap) + int(np.argmax(act[max(0, lo - gap):lo]))
        while hi < n - 1 and np.any(act[hi + 1:hi + 1 + gap]):
            hi = hi + 1 + int(np.max(np.nonzero(act[hi + 1:hi + 1 + gap])))
        cap = int(max_span_s * FS / fr)
        if hi - lo + 1 > cap:
            skipped.append(g["name"] + ":span>cap")
            continue
        kws.append({"name": g["name"], "t_start": a + lo * fr / FS, "t_end": a + (hi + 1) * fr / FS,
                    "peak_db_above_local_floor": round(float(e[pk] - np.percentile(e, 20)), 1)})
    return kws, skipped, None, segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--thresholds", default="0.5,0.6,0.7,0.8,0.9,0.95,0.98")
    ap.add_argument("--n", default="1,3,5")
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    model = pathlib.Path(args.model)
    fe = Frontend()
    thrs = [float(v) for v in args.thresholds.split(",")]
    ns = [int(v) for v in args.n.split(",")]
    report = {"model": str(model), "frontend_sha256": fe.sha256, "stride_frames": STRIDE, "win_frames": WIN,
              "refractory_s": REFRACTORY_S, "runs": {}}
    for rd in args.runs:
        run = pathlib.Path(rd)
        audio = load_run_audio(run)
        t, p, _, _ = posteriors(model, fe.to_int8(fe.features(audio)))
        hours = len(audio) / FS / 3600
        kws, skipped, floor, segs = keyword_ends(run, audio) if (run / "capture_summary.json").exists() else ([], [], None, [])
        rr = {"seconds": round(len(audio) / FS, 1), "keywords_located": len(kws), "keyword_prompts_without_speech": skipped,
              "silence_floor_dbfs_20ms": floor, "sweep": []}
        for n in ns:
            for thr in thrs:
                dets = detect(t, p, thr, n)
                # A detection between the keyword's acoustic start and 1.2 s after its end counts as a hit;
                # lag = detection - acoustic end (negative = fired before the keyword ended: prefix firing, X13).
                # Extra detections inside a keyword prompt are reported separately from true false activations.
                used, hits, lags = set(), {}, []
                for k in kws:
                    m = [d for d in dets if k["t_start"] <= d <= k["t_end"] + 1.2 and d not in used]
                    if m:
                        used.add(m[0])
                        hits[k["name"]] = True
                        lags.append(m[0] - k["t_end"])
                in_kw = [d for d in dets if d not in used and any(k["t_start"] - 0.3 <= d <= k["t_end"] + 2.5 for k in kws)]
                fa = [d for d in dets if d not in used and d not in in_kw]
                fa_where = [next((g["name"] for g in segs if g["t0_s"] <= d < g["t1_s"] + 0.3), "outside_prompts") for d in fa]
                cond = {}
                for k in kws:
                    c = "_".join(k["name"].split("_")[1:3])
                    cond.setdefault(c, [0, 0])
                    cond[c][0] += int(k["name"] in hits)
                    cond[c][1] += 1
                rr["sweep"].append({
                    "n": n, "threshold": thr, "detections": len(dets),
                    "recall": round(len(hits) / len(kws), 4) if kws else None,
                    "recall_by_condition": {c: f"{a}/{b}" for c, a, b in ((c, *v) for c, v in cond.items())},
                    "false_activations": len(fa), "fa_per_hour": round(len(fa) / hours, 2), "exposure_hours": round(hours, 4),
                    "fa_locations": fa_where, "extra_detections_within_keyword_prompts": len(in_kw),
                    "detection_lag_s": {"median": round(float(np.median(lags)), 3), "min": round(float(np.min(lags)), 3),
                                        "max": round(float(np.max(lags)), 3)} if lags else None,
                })
        report["runs"][run.name] = rr
    out = model.parent / f"eval_{args.tag}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name, rr in report["runs"].items():
        print(f"== {name}: {rr['seconds']} s, keywords located {rr['keywords_located']}, no-speech prompts {rr['keyword_prompts_without_speech']}")
        for s in rr["sweep"]:
            print(f"  N={s['n']} thr={s['threshold']:.2f}  recall={s['recall']}  FA={s['false_activations']} "
                  f"(exp {s['exposure_hours']} h)  extra_in_kw={s['extra_detections_within_keyword_prompts']}  "
                  f"lag={s['detection_lag_s']}  by_cond={s['recall_by_condition']}  FA@={s['fa_locations'][:8]}")
    print("->", out)


if __name__ == "__main__":
    main()
