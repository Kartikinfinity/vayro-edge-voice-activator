"""Analyse a capture run (M1 audio-path evidence). Plots are generated only from the saved WAV.

Outputs into the run folder:
  analysis.json    metrics + their definitions
  spectrogram.png  0–8 kHz spectrogram of the whole capture
  psd.png          Welch PSD per segment, with the INMP441 passband edge (0.423·fs) marked
  level.png        100 ms RMS level timeline (dBFS)

Usage:
  python host/analyze_audio.py <run_dir> [--segments "silence:0-5,speech:5-12,hiss:12-16,clap:16-20"]
"""
import argparse
import json
import pathlib
import wave

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402

FS24 = float(2 ** 23)
DEFINITIONS = {
    "rms_dbfs": "AES17: 20*log10(RMS*sqrt(2)/2^23); a full-scale sine reads 0 dBFS",
    "peak_dbfs": "20*log10(max|x|/2^23), sample peak",
    "clip_samples_24": "samples with |x| >= 2^23-1",
    "clip_samples_16": "int16-domain samples (x>>8) with value 32767 or -32768",
    "noise_floor_dbfs": "10th percentile of 100 ms RMS values",
    "zero_run": "run of consecutive samples exactly equal to 0 (24-bit); live mic self-noise makes long runs implausible",
    "band_db": "mean Welch PSD (dB re 1 LSB24^2/Hz) over the band",
    "rolloff_db": "band 7.6-7.95 kHz minus band 5.5-6.5 kHz; INMP441 DS: passband edge 0.423*fs=6768 Hz, -6 dB at 0.5*fs",
}


def read_wav24(path: pathlib.Path):
    with wave.open(str(path), "rb") as w:
        assert w.getsampwidth() == 3 and w.getnchannels() == 1
        fs = w.getframerate()
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.uint8).reshape(-1, 3)
    x = (raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16))
    x = np.where(x & 0x800000, x - (1 << 24), x)
    return x.astype(np.int64), fs


def dbfs(rms):
    return float(20 * np.log10(rms * np.sqrt(2) / FS24)) if rms > 0 else -999.0


def zero_runs(x):
    z = np.concatenate(([0], (x == 0).astype(np.int8), [0]))
    d = np.diff(z)
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    return ends - starts, starts


def band_db(f, pxx, lo, hi):
    m = (f >= lo) & (f <= hi)
    return float(10 * np.log10(np.mean(pxx[m]))) if m.any() and np.mean(pxx[m]) > 0 else None


def metrics(x, fs):
    xf = x.astype(np.float64)
    hop = fs // 10
    n_win = len(x) // hop
    win_rms = np.sqrt(np.mean(xf[: n_win * hop].reshape(n_win, hop) ** 2, axis=1)) if n_win else np.array([0.0])
    win_db = np.array([dbfs(r) for r in win_rms])
    runs, _ = zero_runs(x)
    x16 = x >> 8
    f, pxx = signal.welch(xf, fs=fs, nperseg=1024)
    b = {k: band_db(f, pxx, lo, hi) for k, (lo, hi) in
         {"1-4k": (1000, 4000), "5.5-6.5k": (5500, 6500), "7.0-7.5k": (7000, 7500), "7.6-7.95k": (7600, 7950)}.items()}
    return {
        "samples": int(len(x)),
        "seconds": round(len(x) / fs, 3),
        "dc_lsb24": round(float(np.mean(xf)), 2),
        "rms_dbfs": round(dbfs(float(np.sqrt(np.mean(xf ** 2)))), 2),
        "peak_dbfs": round(float(20 * np.log10(np.max(np.abs(xf)) / FS24)), 2) if np.any(x) else -999.0,
        "int16_rms_lsb": round(float(np.sqrt(np.mean(x16.astype(np.float64) ** 2))), 2),
        "int16_peak_lsb": int(np.max(np.abs(x16))),
        "clip_samples_24": int(np.sum(np.abs(x) >= FS24 - 1)),
        "clip_samples_16": int(np.sum((x16 >= 32767) | (x16 <= -32768))),
        "level_100ms_dbfs": {"p10_noise_floor": round(float(np.percentile(win_db, 10)), 2),
                             "p50": round(float(np.percentile(win_db, 50)), 2),
                             "p90": round(float(np.percentile(win_db, 90)), 2),
                             "max": round(float(np.max(win_db)), 2)},
        "zero_run_longest_samples": int(runs.max()) if runs.size else 0,
        "zero_runs_ge_1ms": int(np.sum(runs >= fs // 1000)),
        "band_db": b,
        "rolloff_db": round(b["7.6-7.95k"] - b["5.5-6.5k"], 2) if b["7.6-7.95k"] is not None and b["5.5-6.5k"] is not None else None,
    }, (f, pxx), win_db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--segments", default="",
                    help='e.g. "silence:0-5,speech:5-12"; default: the prompts recorded by capture.py --script')
    ap.add_argument("--trim", type=float, default=0.7, help="seconds dropped from each scripted segment start (reaction lag)")
    args = ap.parse_args()
    run = pathlib.Path(args.run_dir)
    x, fs = read_wav24(run / "audio_24bit.wav")

    segs = []
    for spec in filter(None, args.segments.split(",")):
        name, _, rng = spec.partition(":")
        a, _, b = rng.partition("-")
        segs.append((name, float(a), float(b)))
    summ = run / "capture_summary.json"
    if not segs and summ.exists():
        s = json.loads(summ.read_text(encoding="utf-8"))
        if s.get("settle_s"):
            segs.append(("settle", 0.0, float(s["settle_s"])))
        segs += [(g["name"], g["t0_s"] + args.trim, g["t1_s"]) for g in s.get("script_segments", [])]

    whole, (f, pxx), win_db = metrics(x, fs)
    seg_results, seg_psd = {}, {"whole": (f, pxx)}
    for name, a, b in segs:
        lo, hi = int(a * fs), min(int(b * fs), len(x))
        if hi - lo < 1024:
            continue
        m, psd, _ = metrics(x[lo:hi], fs)
        seg_results[name] = {"t0_s": a, "t1_s": b, **m}
        seg_psd[name] = psd

    # zero runs >= 1 ms located in time — the first one after I2S start is the mic blanking candidate.
    runs, starts = zero_runs(x)
    long_runs = [{"t_s": round(s / fs, 4), "ms": round(r * 1000 / fs, 2)} for r, s in zip(runs, starts) if r >= fs // 1000]

    result = {"file": "audio_24bit.wav", "fs_hz": fs, "whole": whole, "segments": seg_results,
              "zero_runs_ge_1ms_located_first20": long_runs[:20], "definitions": DEFINITIONS}
    (run / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(10, 4))
    fsg, tsg, sxx = signal.spectrogram(x.astype(np.float64), fs=fs, nperseg=512, noverlap=384)
    ax.pcolormesh(tsg, fsg, 10 * np.log10(sxx + 1e-3), shading="auto", cmap="magma")
    ax.axhline(0.423 * fs, color="c", lw=0.8, ls="--", label="0.423·fs passband edge (DS)")
    ax.set(xlabel="time (s)", ylabel="Hz", title=f"INMP441 capture — {run.name}")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(run / "spectrogram.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, (ff, pp) in seg_psd.items():
        ax.plot(ff, 10 * np.log10(pp + 1e-12), lw=1, label=name)
    ax.axvline(0.423 * fs, color="k", lw=0.8, ls="--", label="0.423·fs = %d Hz" % (0.423 * fs))
    ax.axvline(fs / 2, color="k", lw=0.8, ls=":")
    ax.set(xlabel="Hz", ylabel="dB re 1 LSB24²/Hz", title="Welch PSD (nperseg=1024) — measured")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(run / "psd.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(np.arange(len(win_db)) * 0.1, win_db, lw=1)
    ax.set(xlabel="time (s)", ylabel="dBFS (AES17)", title="100 ms RMS level — measured")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(run / "level.png", dpi=130)
    plt.close(fig)

    print(json.dumps({"whole": whole, "segments": {k: {kk: v[kk] for kk in ("rms_dbfs", "peak_dbfs", "int16_rms_lsb", "rolloff_db")}
                                                   for k, v in seg_results.items()},
                      "zero_runs_ge_1ms": long_runs[:5]}, indent=2))


if __name__ == "__main__":
    main()
