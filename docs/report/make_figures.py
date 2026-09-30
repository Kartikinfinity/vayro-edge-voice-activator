"""Data charts for the technical report, generated ONLY from saved evidence files (no typed-in measurements).

Each chart function reads the raw artefact named in its docstring and writes docs/report/figures/<name>.svg.
Hand-drawn block diagrams live in the same folder as hand-written SVG (they are drawings, not data).

Usage (host venv): python docs/report/make_figures.py
"""
import json
import pathlib
import re
import wave

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
EV = ROOT / "evidence"
OUT = pathlib.Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)

INK, MUTED, GRID = "#1f2933", "#6b7785", "#d9dee4"
EDGE, NET, SRV, WARN, ACC = "#1f5f8b", "#7a5aa6", "#2f7d4f", "#b8591a", "#c2185b"
plt.rcParams.update({
    "svg.fonttype": "none", "font.family": "Segoe UI", "font.size": 8.5, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "legend.frameon": False, "legend.fontsize": 8, "axes.titlesize": 9,
})
POST = np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")])


def save(fig, name):
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight", pad_inches=0.04, metadata={"Date": None})
    plt.close(fig)
    print("wrote", name)


def events(run):
    return [json.loads(x) for x in (EV / "runs" / run / "device_events.jsonl").read_text(encoding="utf-8").splitlines()]


def read_wav(path, start_s=0.0, dur_s=None):
    with wave.open(str(path)) as w:
        fs = w.getframerate()
        w.setpos(int(start_s * fs))
        n = w.getnframes() - int(start_s * fs) if dur_s is None else int(dur_s * fs)
        return np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64), fs


def psd_m1():
    """evidence/runs/20260926_214931_m1_msb_settle_warm/audio_16bit.wav, steady room segment 8-26 s (E-02, E-03)."""
    x, fs = read_wav(EV / "runs/20260926_214931_m1_msb_settle_warm/audio_16bit.wav", 8.0, 18.0)
    f, p = signal.welch(x, fs, nperseg=1024)
    db = 10 * np.log10(p * 2 / (32768.0 ** 2) + 1e-20)  # dBFS/Hz (full-scale sine = 0 dBFS reference)
    fig, ax = plt.subplots(figsize=(6.4, 2.5))
    ax.axvspan(125, 6500, color=EDGE, alpha=0.07, lw=0)
    ax.plot(f, db, color=EDGE, lw=1.1)
    ax.axvline(6768, color=WARN, lw=1, ls="--")
    ax.text(6768 + 60, db.max() - 4, "0.423·fs = 6 768 Hz\n(INMP441 pass-band edge)", color=WARN, fontsize=7.5, va="top")
    ax.text(300, db.min() + 6, "mel filterbank range 125–6 500 Hz", color=EDGE, fontsize=7.5)
    ax.set_xlim(0, 8000)
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("power (dBFS/Hz)")
    save(fig, "psd_m1")


def posterior_s01s3():
    """evidence/runs/20260927_195253_kw_S01_s3: posteriors_device.bin (v2b live on the device) + script_segments."""
    run = EV / "runs/20260927_195253_kw_S01_s3"
    d = np.fromfile(run / "posteriors_device.bin", dtype=POST)
    t = (480 + 160 * d["frame"].astype(np.int64)) / 16000
    p = (d["raw"].astype(np.float32) + 128) / 256  # output quantisation of v2b: scale 1/256, zero point -128
    m3 = np.convolve(p, np.ones(3) / 3, mode="full")[:len(p)]
    segs = json.loads((run / "capture_summary.json").read_text(encoding="utf-8"))["script_segments"]
    lo, hi = 7.0, 58.0
    w = (t >= lo) & (t <= hi)
    fig, ax = plt.subplots(figsize=(6.6, 2.4))
    kw = [g for g in segs if g["name"].startswith("kw_") and g["t1_s"] > lo and g["t0_s"] < hi]
    for j, g in enumerate(kw):
        if j % 2 == 0:
            ax.axvspan(g["t0_s"], g["t1_s"], color=EDGE, alpha=0.08, lw=0)
    ax.plot(t[w], p[w], color=MUTED, lw=0.7, label="model score p (every 60 ms)")
    ax.plot(t[w], m3[w], color=EDGE, lw=1.3, label="mean of last 3 scores")
    ax.axhline(0.80, color=WARN, lw=1, ls="--", label="threshold 0.80")
    tr = t[(d["trig"] > 0) & w]
    ax.plot(tr, np.full(len(tr), 1.04), "v", color=ACC, ms=5, label="trigger (device, live)", clip_on=False)
    ax.set_xlim(lo, hi)
    ax.set_ylim(0, 1.08)
    ax.set_xlabel("session time (s) — alternate shading marks the 4 s 'Say: Hey Vayro' prompt windows")
    ax.set_ylabel("posterior")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=4)
    save(fig, "posterior_s01s3")


def night_fa():
    """evidence/runs/20260927_203133_ambient_night_20260927/posteriors_device.bin (v2b live trigger flags, 10 h)."""
    d = np.fromfile(EV / "runs/20260927_203133_ambient_night_20260927/posteriors_device.bin", dtype=POST)
    t = (480 + 160 * d["frame"].astype(np.int64)) / 16000
    counts = np.histogram(t[d["trig"] > 0] / 3600, bins=np.arange(0, 11))[0]
    labels = [f"{(20 + h) % 24:02d}:31" for h in range(10)]
    fig, ax = plt.subplots(figsize=(6.4, 2.2))
    colors = [WARN if h < 2 else (EDGE if h < 5 else SRV) for h in range(10)]
    ax.bar(np.arange(10), counts, color=colors, width=0.75)
    for h, c in enumerate(counts):
        ax.text(h, c + 0.3, str(c), ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(np.arange(10), labels)
    ax.set_ylabel("false triggers per hour")
    ax.set_ylim(0, max(counts) + 3)
    ax.text(2.2, 12.5, "household awake\n(TV, family talk)", ha="left", fontsize=7.5, color=WARN)
    ax.text(3.0, 5.5, "asleep — training hours\n(c002–c004)", ha="center", fontsize=7.5, color=EDGE)
    ax.text(7.0, 5.5, "asleep — declared HELD-OUT\nblock c005–c009 (5 h)", ha="center", fontsize=7.5, color=SRV)
    ax.set_xlabel("hour starting at (27–28 Sep)")
    save(fig, "night_fa")
    return counts.tolist()


def cpu_final():
    """evidence/runs/20260929_202327_final_v2b_confirm/device_events.jsonl: @CPU windows (FreeRTOS run-time stats)."""
    ev = events("20260929_202327_final_v2b_confirm")
    cpu = [e for e in ev if e["type"] == "CPU"]
    t0 = min(e["host_t"] for e in ev if e["type"] == "KW")
    t = np.array([e["host_t"] for e in cpu])
    c0 = np.array([e["core0_busy"] for e in cpu])
    c1 = np.array([e["core1_busy"] for e in cpu])
    fig, ax = plt.subplots(figsize=(6.4, 2.4))
    ax.axvspan(t0, t.max() + 5, color=NET, alpha=0.07, lw=0)
    ax.plot(t, c1, "o-", color=EDGE, ms=2.5, lw=1, label="core 1 busy (audio pipeline)")
    ax.plot(t, c0, "o-", color=SRV, ms=2.5, lw=1, label="core 0 busy (Wi-Fi, streamer)")
    ax.plot(t, (c0 + c1) / 2, "-", color=MUTED, lw=1, label="both cores averaged")
    ax.axhline(10, color=WARN, lw=1, ls="--")
    ax.text(5, 10.25, "10 % (PS limit, idle listening)", color=WARN, fontsize=7.5)
    ax.text(t0 + 5, 1.2, "30 synthetic streams, one every 10 s (not idle)", color=NET, fontsize=7.5)
    ax.text(10, 7.0, "idle listening", color=INK, fontsize=7.5)
    ax.set_ylim(0, 12)
    ax.set_xlabel("time since boot (s); one point = one 10 s window")
    ax.set_ylabel("CPU busy (%)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=3)
    save(fig, "cpu_final")
    idle = t < t0
    return {"idle_windows": int(idle.sum()), "core1_idle_mean": round(float(c1[idle].mean()), 2),
            "core1_idle_max": round(float(c1[idle].max()), 2), "core0_idle_mean": round(float(c0[idle].mean()), 2),
            "c3_idle_mean": round(float(((c0 + c1) / 2)[idle].mean()), 2),
            "stream_windows": int((~idle).sum()), "core1_stream_mean": round(float(c1[~idle].mean()), 2),
            "core1_stream_max": round(float(c1[~idle].max()), 2), "core0_stream_mean": round(float(c0[~idle].mean()), 2)}


def latency_t1():
    """evidence/server/20260930_085548/latency_report.json (T1, E-63)."""
    r = json.loads((EV / "server/20260930_085548/latency_report.json").read_text(encoding="utf-8"))
    a = r["activations"]
    n = np.arange(1, len(a) + 1)
    lag = np.array([x["lag_audio_ms"] for x in a])
    l1 = np.array([x["L1_audio0_ms"] for x in a])
    fig, ax = plt.subplots(figsize=(6.4, 2.5))
    ax.barh(n, lag, color=EDGE, label="keyword end → detection (on-device decision, measured in the stream)")
    ax.barh(n, np.full(len(a), 10.0), left=lag, color="white", edgecolor=MUTED, hatch="////", lw=0.5,
            label="capture term, estimated 10 ± 7 ms")
    ax.barh(n, l1, left=lag + 10, color=SRV, label="detection → first audio at the server (measured)")
    med = r["summary"]["L2_est_ms"]["p50"]
    ax.axvline(med, color=WARN, lw=1, ls="--")
    ax.text(med + 3, 12.6, f"median {med:.0f} ms", color=WARN, fontsize=7.5)
    ax.set_yticks(n)
    ax.set_ylim(0.3, 13.2)
    ax.invert_yaxis()
    ax.set_xlabel("keyword end → first audio at the ASR server (ms)")
    ax.set_ylabel("activation")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.27), ncol=1)
    save(fig, "latency_t1")
    return r["summary"]


def _diram(log):
    t = (EV / log).read_text(encoding="utf-8", errors="ignore")
    return int(re.search(r"DIRAM\s*│\s*(\d+)", t).group(1))


def _heap_peak(run):
    ev = events(run)
    total = next(e["int_total"] for e in ev if e["type"] == "MEM")
    return total - min(e["heap_min"] for e in ev if e["type"] == "STATS")


def memory_progress():
    """Static DIRAM from the idf size logs + peak heap (int_total - lowest heap_min) from the runs (E-42 ... E-60)."""
    rows = [("E-42\nnon-streaming\n28 Sep 07:53", "exp1_product_build_v2.log", "20260928_075330_exp1_product_runtime_v2"),
            ("E-52\nstreaming\n28 Sep 22:26", "exp1_streaming_size.log", "20260928_222620_exp1_product_streaming"),
            ("E-53\nafter DEC-24\n28 Sep 22:55", "exp1_streaming_size_dec24.log", "20260928_225547_exp1_product_streaming_dec24"),
            ("E-58\nv4 final\n29 Sep 19:46", "final_product_size_v4.log", "20260929_194642_final_v4_streaming"),
            ("E-60\nv2b final\n29 Sep 20:23", "final_product_size_v2b.log", "20260929_202327_final_v2b_confirm")]
    st = np.array([_diram(log) for _, log, _ in rows])
    hp = np.array([_heap_peak(run) for _, _, run in rows])
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    ax.bar(x, st / 1000, color=EDGE, width=0.6, label="static internal RAM (.bss + IRAM code + .data + vectors)")
    ax.bar(x, hp / 1000, bottom=st / 1000, color="#8fb6d3", width=0.6, label="peak heap (Wi-Fi, lwIP, task stacks, front end)")
    for i, (s_, h) in enumerate(zip(st, hp)):
        ax.text(i, (s_ + h) / 1000 - 14, f"{s_ + h:,}\nbytes", ha="center", fontsize=7.2, color=INK)
        ax.text(i, s_ / 1000 / 2, f"{s_:,}", ha="center", fontsize=7, color="white")
    ax.axhline(256.0, color=WARN, lw=1, ls="--")
    ax.axhline(262.144, color=WARN, lw=0.8, ls=":")
    ax.text(len(rows) - 0.62, 249.5, "256 kB = 256 000 B", color=WARN, fontsize=7.2, ha="left", va="top")
    ax.text(len(rows) - 0.62, 264.5, "256 KiB = 262 144 B", color=WARN, fontsize=7.2, ha="left", va="bottom")
    ax.set_xlim(-0.5, len(rows) + 0.6)
    ax.set_xticks(x, [r[0] for r in rows], fontsize=7.2)
    ax.set_ylim(0, 290)
    ax.set_ylabel("peak internal RAM, S4 (kB)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.34), ncol=1)
    save(fig, "memory_progress")
    return [{"label": r[0].split("\n")[0], "static": int(s), "heap_peak": int(h), "S4": int(s + h)} for r, s, h in zip(rows, st, hp)]


def accuracy_compare():
    """model/artifacts: v2b/v4 eval_test_S01_s3.json, eval_newspk_S02_s1.json, prompt_hits_*_m6_v3_S01.json,
    household_compare_20260928.json (M6 v2 hits) and selection_v4_outcome.json (held-out FA counts)."""
    art = ROOT / "model" / "artifacts"

    def prompt_hits(model, fname, thr):
        r = json.loads((art / model / fname).read_text(encoding="utf-8"))
        for rr in r["runs"].values():
            for s in rr["sweep"]:
                if s["n"] == 3 and abs(s["threshold"] - thr) < 1e-6:
                    ps = s["prompt_score"]
                    return ps["kw_prompts_hit"], ps["kw_prompts"]
    ph = json.loads((art / "prompt_hits_20260929_192230_m6_v3_S01.json").read_text(encoding="utf-8"))["models"]
    v4sel = json.loads((art / "selection_v4_outcome.json").read_text(encoding="utf-8"))
    m6v2 = {"v2b": (6, 10), "v4": (8, 10)}  # selection_v4_outcome.json reported_not_in_rule (M6 v2 prompts)
    sets = [("S01 session 3\n(held-out session)", prompt_hits("v2b", "eval_test_S01_s3.json", 0.8), prompt_hits("v4", "eval_test_S01_s3.json", 0.7)),
            ("S02 — new speaker\n(never trained on)", prompt_hits("v2b", "eval_newspk_S02_s1.json", 0.8), prompt_hits("v4", "eval_newspk_S02_s1.json", 0.7)),
            ("M6 v3 commands\n(S01, fresh)", (ph["v2b"]["hits"], ph["v2b"]["of"]), (ph["v4"]["hits"], ph["v4"]["of"])),
            ("M6 v2 commands\n(S01, TV on)", m6v2["v2b"], m6v2["v4"])]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(6.6, 2.5), gridspec_kw={"width_ratios": [3, 1.5]})
    x = np.arange(len(sets))
    for k, (name, col, off) in enumerate((("v2b @ 0.80 (shipped)", EDGE, -0.18), ("v4 @ 0.70", NET, 0.18))):
        vals = [s[1 + k][0] / s[1 + k][1] * 100 for s in sets]
        ax.bar(x + off, vals, width=0.34, color=col, label=name)
        for i, s in enumerate(sets):
            ax.text(x[i] + off, vals[i] + 2, f"{s[1 + k][0]}/{s[1 + k][1]}", ha="center", fontsize=7)
    ax.set_xticks(x, [s[0] for s in sets], fontsize=7)
    ax.set_ylim(0, 115)
    ax.set_ylabel("keyword prompts detected (%)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2)
    fa = [("household\nheld-out 0.86 h", v4sel["a_household_heldout_s5_ge_3600s"]["v2b@0.80"], v4sel["a_household_heldout_s5_ge_3600s"]["v4@0.70"]),
          ("quiet night\nheld-out 5 h", v4sel["c_heldout_night_c005_c009"]["v2b@0.80"], v4sel["c_heldout_night_c005_c009"]["v4@0.70"])]
    y = np.arange(len(fa))
    bx.bar(y - 0.18, [f[1] for f in fa], width=0.34, color=EDGE)
    bx.bar(y + 0.18, [f[2] for f in fa], width=0.34, color=NET)
    for i, f in enumerate(fa):
        bx.text(i - 0.18, f[1] + 0.3, str(f[1]), ha="center", fontsize=7)
        bx.text(i + 0.18, f[2] + 0.3, str(f[2]), ha="center", fontsize=7)
    bx.set_xticks(y, [f[0] for f in fa], fontsize=7)
    bx.set_ylabel("false triggers (count)")
    fig.tight_layout(w_pad=2.0)
    save(fig, "accuracy_compare")
    return sets, fa


if __name__ == "__main__":
    summary = {"psd_m1": psd_m1(), "posterior_s01s3": posterior_s01s3(), "night_fa_per_hour": night_fa(),
               "cpu_final": cpu_final(), "latency_t1": latency_t1(), "memory_progress": memory_progress(),
               "accuracy_compare": accuracy_compare()}
    (OUT / "figure_data_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k in ("cpu_final", "memory_progress", "night_fa_per_hour")}, indent=1))
