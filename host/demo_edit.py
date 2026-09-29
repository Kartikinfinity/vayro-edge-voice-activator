"""Assemble the demo video from two real-time takes of host/demo_session.py (no speed changes, no cuts inside a take).

  title card -> DEMO take (screen, real time) with the device's own microphone audio -> part-2 card ->
  EFFICIENCY take (product firmware, real time) -> end card with measured results (evidence-ledger IDs)

Audio alignment: the capture run's audio_16bit.wav starts at device audio sample 0; every @KW line carries t_ms = audio
time of the detection, and the dashboard logged the wall time it read that line. wall(sample 0) = median(wall_read -
0.03 s - t_ms/1000). Video: the dashboard logged the wall time of a white sync frame, found here in screen.mp4.
Audio processing: 100 Hz high-pass + one fixed gain (speech to about -16 dBFS) + soft limiter; nothing else.

Usage (host venv): python host/demo_edit.py --demo <evidence/demo/..._demo> --eff <evidence/demo/..._efficiency>
Output: evidence/demo/PS26172_demo_video.mp4 (+ edit_meta.json)
"""
import argparse
import json
import pathlib
import re
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import signal

ROOT = pathlib.Path(__file__).resolve().parents[1]
FF = imageio_ffmpeg.get_ffmpeg_exe()
TEAM = json.loads((ROOT / "docs" / "submission" / "team.json").read_text(encoding="utf-8"))
FONT = "C:/Windows/Fonts/"
W, H, FPS, SR = 1920, 1080, 30, 16000
BG, TXT, MUTED, ORANGE, GREEN, BLUE = (11, 18, 32), (230, 237, 247), (143, 163, 191), (245, 158, 11), (34, 197, 94), \
    (56, 189, 248)


def font(name, size):
    return ImageFont.truetype(FONT + name, size)


def card(path, lines):
    """lines: (text, font_file, size, color, gap_before_px)"""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    y = 170
    for text, ff, sz, col, gap in lines:
        y += gap
        f = font(ff, sz)
        d.text((150, y), text, font=f, fill=col)
        y += int(sz * 1.35)
    im.save(path)


def flash_time(video):
    """pts (s) of the first near-white frame (the dashboard's sync flash)."""
    p = subprocess.run([FF, "-hide_banner", "-i", str(video), "-vf", "scale=16:10,format=gray,showinfo", "-f", "rawvideo",
                        "-"], capture_output=True)
    pts = [float(m) for m in re.findall(rb"pts_time:([\d.]+)", p.stderr)]
    frames = np.frombuffer(p.stdout, np.uint8).reshape(-1, 160).mean(axis=1)
    n = min(len(pts), len(frames))
    idx = np.nonzero(frames[:n] > 230)[0]
    if not len(idx):
        raise SystemExit(f"no sync flash found in {video}")
    k = int(idx[0])
    dur = pts[n - 1]
    return pts[k], dur


def take_info(d):
    d = pathlib.Path(d)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    ev = [json.loads(l) for l in open(d / "events.jsonl", encoding="utf-8")]
    run = None
    for l in open(d / "device.log", encoding="utf-8"):
        m = re.search(r"Saved run: (.+)$", l.strip())
        if m:
            run = pathlib.Path(m.group(1).strip())
    tf, dur = flash_time(d / "screen.mp4")
    return {"dir": d, "meta": meta, "events": ev, "run": run, "t_flash": tf, "dur": dur}


def demo_audio(info, t_start, t_len):
    kws = [e for e in info["events"] if e["kind"] == "kw"]
    if not kws:
        raise SystemExit("no keyword detections in the demo take: nothing to align the audio with")
    wall0 = float(np.median([e["wall"] - 0.03 - e["t_ms"] / 1000 for e in kws]))
    with wave.open(str(info["run"] / "audio_16bit.wav")) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64)
    w_start = info["meta"]["sync_flash_wall"] + (t_start - info["t_flash"])
    s0 = int(round((w_start - wall0) * SR))
    n = int(round(t_len * SR))
    out = np.zeros(n)
    src_lo, dst_lo = max(0, s0), max(0, -s0)
    m = max(0, min(n - dst_lo, len(x) - src_lo))
    out[dst_lo:dst_lo + m] = x[src_lo:src_lo + m]
    y = signal.sosfilt(signal.butter(4, 100, btype="high", fs=SR, output="sos"), out)
    fr = 800
    k = len(y) // fr
    lev = np.sqrt(np.mean(y[: k * fr].reshape(k, fr) ** 2, axis=1))
    speech = np.percentile(lev[lev > 0], 97) if np.any(lev > 0) else 1.0
    g = 10 ** (-16 / 20) * 32768 / np.sqrt(2) / max(speech, 1.0)
    y = np.tanh(y * g / 30000) * 30000  # soft limiter
    return y.astype(np.int16), {"wall0": wall0, "s0": s0, "gain_db": round(20 * np.log10(g), 1),
                                "kw_used": len(kws)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True)
    ap.add_argument("--eff", required=True)
    ap.add_argument("--out", default=str(ROOT / "evidence" / "demo" / "PS26172_demo_video.mp4"))
    args = ap.parse_args()
    work = pathlib.Path(args.out).with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    dm, ef = take_info(args.demo), take_info(args.eff)
    team = TEAM["team_name"]
    card(work / "title.png", [
        ("SMART INDIA HACKATHON 2026  \u00b7  PROBLEM STATEMENT 26172", "seguisb.ttf", 34, MUTED, 0),
        ("Low Latency and Efficient Voice Activator", "seguisb.ttf", 74, TXT, 30),
        ("for Edge Devices", "seguisb.ttf", 74, TXT, 0),
        ("Hey Vayro \u2014 on-device wake word, cloud ASR only after the keyword", "segoeui.ttf", 40, ORANGE, 30),
        (f"Team: {team}", "segoeui.ttf", 36, TXT, 40),
        ("Live demonstration on the physical prototype: ESP32-S3 + INMP441 microphone", "segoeui.ttf", 32, MUTED, 40),
        ("Screen recorded in real time \u00b7 a real person speaking to the board \u00b7 no AI-generated voice or video",
         "segoeui.ttf", 30, GREEN, 6)])
    card(work / "part2.png", [
        ("PART 2", "seguisb.ttf", 34, MUTED, 60),
        ("Efficiency \u2014 product firmware", "seguisb.ttf", 72, TXT, 20),
        ("The configuration judged against the PS limits (< 256 KB RAM, < 10 % CPU while idle-listening):",
         "segoeui.ttf", 34, TXT, 40),
        ("same model v2b, no USB audio stream. Live device lines, real time.", "segoeui.ttf", 34, TXT, 4)])
    card(work / "end.png", [
        ("MEASURED RESULTS  (evidence ledger IDs in brackets)", "seguisb.ttf", 34, MUTED, -40),
        ("Peak RAM while streaming   245.0 KiB  (< 256 KB)   [E-60]", "consola.ttf", 40, TXT, 30),
        ("Idle CPU                   5.5 % both cores, busiest core \u2264 9.5 %   [E-60]", "consola.ttf", 40, TXT, 6),
        ("Model                      28 KB int8, 10.7 k params, runs every 60 ms", "consola.ttf", 40, TXT, 6),
        ("Keyword end \u2192 server      \u2248 95 ms median, p95 136 ms   [E-37]", "consola.ttf", 40, TXT, 6),
        ("Keyword accuracy           22/25 speaker 1, 20/25 new speaker   [E-59]", "consola.ttf", 40, TXT, 6),
        ("False triggers             1 in 5 h quiet night; 15.1 /h with TV   [E-51]", "consola.ttf", 40, ORANGE, 6),
        ("Open source only \u00b7 custom keyword trained from scratch \u00b7 no vendor voice SDK", "segoeui.ttf", 32,
         GREEN, 40),
        (f"Raw logs of these takes: evidence/demo/{dm['dir'].name}, {ef['dir'].name}", "segoeui.ttf", 26, MUTED, 20)])
    # segments (real time, only the part before the sync flash is dropped)
    d0 = dm["t_flash"] + 0.6
    d_len = dm["dur"] - d0
    e0 = ef["t_flash"] + 0.6
    e_len = ef["dur"] - e0
    T_TITLE, T_P2, T_END = 7.0, 5.0, 12.0
    audio, ainfo = demo_audio(dm, d0, d_len)
    total = T_TITLE + d_len + T_P2 + e_len + T_END
    track = np.zeros(int(round(total * SR)), np.int16)
    a0 = int(round(T_TITLE * SR))
    track[a0:a0 + len(audio)] = audio[: len(track) - a0]
    with wave.open(str(work / "audio.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(track.tobytes())
    fit = f"scale=1728:1080:flags=lanczos,pad={W}:{H}:96:0:color=0x0B1220,setsar=1,fps={FPS},format=yuv420p"
    still = f"scale={W}:{H},setsar=1,fps={FPS},format=yuv420p"
    fc = (f"[0:v]{still}[t];"
          f"[1:v]trim=start={d0:.3f}:duration={d_len:.3f},setpts=PTS-STARTPTS,{fit}[d];"
          f"[2:v]{still}[p];"
          f"[3:v]trim=start={e0:.3f}:duration={e_len:.3f},setpts=PTS-STARTPTS,{fit}[e];"
          f"[4:v]{still}[z];"
          f"[t][d][p][e][z]concat=n=5:v=1:a=0[v]")
    cmd = [FF, "-hide_banner", "-loglevel", "error", "-y",
           "-loop", "1", "-t", str(T_TITLE), "-i", str(work / "title.png"),
           "-i", str(dm["dir"] / "screen.mp4"),
           "-loop", "1", "-t", str(T_P2), "-i", str(work / "part2.png"),
           "-i", str(ef["dir"] / "screen.mp4"),
           "-loop", "1", "-t", str(T_END), "-i", str(work / "end.png"),
           "-i", str(work / "audio.wav"),
           "-filter_complex", fc, "-map", "[v]", "-map", "5:a",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", args.out]
    subprocess.run(cmd, check=True)
    meta = {"out": args.out, "demo_take": str(dm["dir"]), "efficiency_take": str(ef["dir"]),
            "demo_capture_run": str(dm["run"]), "demo_segment_s": [round(d0, 3), round(d_len, 3)],
            "efficiency_segment_s": [round(e0, 3), round(e_len, 3)], "audio": ainfo,
            "processing": "no speed change; only frames before each take's sync flash dropped; audio = device "
                          "microphone (capture build), 100 Hz high-pass + fixed gain + soft limiter"}
    (work / "edit_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
