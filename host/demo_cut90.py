"""Cut the final 90.0 s demo video from two real-time takes of host/demo_take.py. No speed change, no overlays, no cards.

  0-68 s   DEMO take: from 4 s before the first prompt to the end of the no-keyword part (t0-4 .. t0+64), with the
           device's own microphone audio (capture build) aligned to the screen
  68-90 s  EFFICIENCY take (product firmware): 22 s from the boot lines through the @CPU idle readings; silent

Alignment: video <-> wall clock from the prompt window's white sync flash (its wall time is logged); device audio
sample 0 <-> wall clock from the @KW events (host_t0_epoch + host_t - 0.03 s - t_ms/1000, median).
Audio processing: 100 Hz high-pass, one fixed gain (speech ~ -16 dBFS), soft limiter, 150 ms fades at the cut.
Usage (host venv): python host/demo_cut90.py --demo <take> --eff <take> [--out evidence/demo/PS26172_demo_90s.mp4]
"""
import argparse
import json
import pathlib
import re
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from scipy import signal

ROOT = pathlib.Path(__file__).resolve().parents[1]
FF = imageio_ffmpeg.get_ffmpeg_exe()
SR, FPS = 16000, 30
A_LEN, B_LEN = 68.0, 22.0


def flash_time(video, rect):
    x, y, w, h = rect
    p = subprocess.run([FF, "-hide_banner", "-i", str(video), "-vf", f"crop={w}:{h}:{x}:{y},scale=16:10,format=gray,"
                        "showinfo", "-f", "rawvideo", "-"], capture_output=True)
    pts = [float(m) for m in re.findall(rb"pts_time:([\d.]+)", p.stderr)]
    fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, 160).mean(axis=1)
    n = min(len(pts), len(fr))
    idx = np.nonzero(fr[:n] > 200)[0]
    if not len(idx):
        raise SystemExit(f"no sync flash in {video}")
    return pts[int(idx[0])], pts[n - 1]


def load(take):
    take = pathlib.Path(take)
    meta = json.loads((take / "meta.json").read_text(encoding="utf-8"))
    run = pathlib.Path(meta["capture_run"])
    summ = json.loads((run / "capture_summary.json").read_text(encoding="utf-8"))
    ev = [json.loads(l) for l in open(run / "device_events.jsonl", encoding="utf-8")]
    tf, dur = flash_time(take / "screen.mp4", meta["rects"]["prompt"])
    return {"take": take, "meta": meta, "run": run, "epoch": summ["host_t0_epoch"], "ev": ev, "tf": tf, "dur": dur}


def vt(t, wall):
    """video time (s) of a wall-clock instant in take t"""
    return t["tf"] + (wall - t["meta"]["flash_wall"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True)
    ap.add_argument("--eff", required=True)
    ap.add_argument("--out", default=str(ROOT / "evidence" / "demo" / "PS26172_demo_90s.mp4"))
    args = ap.parse_args()
    A, B = load(args.demo), load(args.eff)
    # --- segment A: t0-4 .. t0+64
    a_wall = A["meta"]["t0"] - 4.0
    a0 = vt(A, a_wall)
    kws = [e for e in A["ev"] if e["type"] == "KW" and "t_ms" in e]
    if not kws:
        raise SystemExit("no keyword detections in the demo take")
    wall0 = float(np.median([A["epoch"] + e["host_t"] - 0.03 - float(e["t_ms"]) / 1000 for e in kws]))
    with wave.open(str(A["run"] / "audio_16bit.wav")) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64)
    s0 = int(round((a_wall - wall0) * SR))
    n = int(A_LEN * SR)
    seg = np.zeros(n)
    lo, dlo = max(0, s0), max(0, -s0)
    m = max(0, min(n - dlo, len(x) - lo))
    seg[dlo:dlo + m] = x[lo:lo + m]
    y = signal.sosfilt(signal.butter(4, 100, btype="high", fs=SR, output="sos"), seg)
    fr = 800
    lev = np.sqrt(np.mean(y[: len(y) // fr * fr].reshape(-1, fr) ** 2, axis=1))
    g = 10 ** (-16 / 20) * 32768 / np.sqrt(2) / max(float(np.percentile(lev, 97)), 1.0)
    y = np.tanh(y * g / 30000) * 30000
    f = int(0.15 * SR)
    y[:f] *= np.linspace(0, 1, f)
    y[-f:] *= np.linspace(1, 0, f)
    track = np.concatenate([y, np.zeros(int(B_LEN * SR))]).astype(np.int16)
    work = pathlib.Path(args.out).with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    with wave.open(str(work / "audio.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(track.tobytes())
    # --- segment B: from 1 s before the boot line; shifted so the 2nd @CPU reading is on screen
    boot = next(e for e in B["ev"] if e["type"] == "BOOT")
    cpus = [e for e in B["ev"] if e["type"] == "CPU"]
    b_wall = B["epoch"] + boot["host_t"] - 1.0
    if len(cpus) >= 2 and B["epoch"] + cpus[1]["host_t"] > b_wall + B_LEN - 1.5:
        b_wall = B["epoch"] + cpus[1]["host_t"] - (B_LEN - 1.5)
    b0 = vt(B, b_wall)
    for name, t, s, L in (("demo", A, a0, A_LEN), ("efficiency", B, b0, B_LEN)):
        if s < 0 or s + L > t["dur"] + 0.05:
            raise SystemExit(f"{name} segment {s:.2f}+{L} s is outside its recording (0..{t['dur']:.2f} s)")
    fit = "scale=-2:1080:flags=lanczos,pad=1920:1080:(ow-iw)/2:0:color=black,setsar=1,fps=30,format=yuv420p"
    fc = (f"[0:v]trim=start={a0:.3f}:duration={A_LEN},setpts=PTS-STARTPTS,{fit}[a];"
          f"[1:v]trim=start={b0:.3f}:duration={B_LEN},setpts=PTS-STARTPTS,{fit}[b];[a][b]concat=n=2:v=1:a=0[v]")
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", str(A["take"] / "screen.mp4"),
                    "-i", str(B["take"] / "screen.mp4"), "-i", str(work / "audio.wav"), "-filter_complex", fc,
                    "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v",
                    "high", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", "90",
                    args.out], check=True)
    meta = {"out": args.out, "demo_take": str(A["take"]), "efficiency_take": str(B["take"]),
            "demo_segment_video_s": round(a0, 3), "efficiency_segment_video_s": round(b0, 3),
            "audio_wall0": wall0, "audio_s0": s0, "gain_db": round(20 * np.log10(g), 1), "kw_used": len(kws),
            "rule": "real time; the only edit is one cut between the two takes"}
    (work / "cut_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
