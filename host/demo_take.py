"""Record one real-time take for the demo video: a black backdrop plus three REAL console windows (ASR server, ESP32-S3
device console, prompt), captured by ffmpeg in exactly their screen rectangle (never the rest of the desktop).

  --mode demo        capture firmware (model v2b + USB microphone audio): prompts for 4 keyword+command utterances (13 s
                     each) and 12 s of talking without the keyword, starting 5 s after the board connects
  --mode efficiency  product firmware: boot + idle listening, ~40 s

Output: evidence/demo/<stamp>_<mode>_term/ {screen.mp4, meta.json, flash.json, ...}; the device run is saved by capture.py.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import time

import imageio_ffmpeg

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv-host" / "Scripts" / "python.exe")
FF = imageio_ffmpeg.get_ffmpeg_exe()
ASR_MODEL = r"D:\ps26172_ext\vosk\vosk-model-en-in-0.5"
REGION = (0, 0, 1440, 852)  # above the taskbar
RECTS = {"server": (0, 0, 620, 852), "device": (620, 0, 820, 600), "prompt": (620, 600, 820, 252)}
FONTS = {"server": 17, "device": 16, "prompt": 26}


def window(name, title, cmd):
    x, y, w, h = RECTS[name]
    return subprocess.Popen(["conhost.exe", PY, str(ROOT / "host" / "term.py"), "--title", title, "--rect",
                             f"{x},{y},{w},{h}", "--font", str(FONTS[name]), "--"] + cmd, cwd=ROOT)


def listening(port=5005):
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    return re.search(rf"0\.0\.0\.0:{port}\s+0\.0\.0\.0:0\s+LISTENING", out) is not None


def kill_tree(p):
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["demo", "efficiency"], required=True)
    args = ap.parse_args()
    take = ROOT / "evidence" / "demo" / f"{dt.datetime.now():%Y%m%d_%H%M%S}_{args.mode}_term"
    take.mkdir(parents=True)
    meta = {"mode": args.mode, "region": REGION, "rects": RECTS, "fonts": FONTS, "started": time.time()}
    procs = {}
    if listening():
        sys.exit("port 5005 is already in use - stop the other server first")
    procs["backdrop"] = subprocess.Popen([PY, "-c", "import tkinter as tk; r=tk.Tk(); r.attributes('-fullscreen', True); "
                                          "r.configure(bg='black', cursor='none'); r.after(400000, r.destroy); r.mainloop()"])
    time.sleep(1.0)
    srv = [PY, "-u", "server/ingest.py", "--port", "5005", "--print-style", "compact", "--status-file",
           str(take / "status.txt")]
    srv += (["--asr", ASR_MODEL, "--min-after-s", "0.8", "--stream-s-max", "6"] if args.mode == "demo"
            else ["--stream-s", "3.0"])
    procs["server"] = window("server", "ASR server (PC)", srv)
    t = time.time()
    while not listening():
        if time.time() - t > 120:
            sys.exit("server did not start")
        time.sleep(0.3)
    procs["prompt"] = window("prompt", "Prompt", [PY, "host/prompt_window.py", "--take", str(take), "--mode", args.mode])
    time.sleep(1.5)
    x, y, w, h = REGION
    rec = subprocess.Popen([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab", "-framerate", "30",
                            "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-draw_mouse", "0",
                            "-i", "desktop", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt",
                            "yuv420p", str(take / "screen.mp4")], stdin=subprocess.PIPE)
    meta["recording_started"] = time.time()
    time.sleep(1.5)
    (take / "flash_request.txt").write_text("1")
    while not (take / "flash.json").exists():
        time.sleep(0.05)
    time.sleep(0.8)
    label = "demo90_" + args.mode
    title = ("ESP32-S3 device console (USB)  -  demo build: model v2b + mic audio for this video" if args.mode == "demo"
             else "ESP32-S3 device console (USB)  -  product firmware")
    wall_s = "110" if args.mode == "demo" else "45"
    procs["device"] = window("device", title, [PY, "-u", "host/capture.py", "--port", "COM7", "--wall-s", wall_s,
                                               "--color", "--label", label, "--note", f"90 s demo video take ({args.mode})"])
    meta["device_started"] = time.time()
    if args.mode == "demo":
        t = time.time()
        while "connected" not in ((take / "status.txt").read_text() if (take / "status.txt").exists() else ""):
            if time.time() - t > 90:
                break
            time.sleep(0.1)
        t0 = time.time() + 5.0
        (take / "start_epoch.txt").write_text(f"{t0:.3f}")
        meta["t0"] = t0
        while time.time() < t0 + 64 + 3:
            time.sleep(0.2)
    else:
        time.sleep(40)
        (take / "stop.txt").write_text("1")
    time.sleep(1.0)
    rec.stdin.write(b"q")
    rec.stdin.flush()
    rec.wait(30)
    meta["recording_stopped"] = time.time()
    try:
        procs["device"].wait(90)  # capture.py ends at --wall-s and saves its run
    except subprocess.TimeoutExpired:
        pass
    time.sleep(3)  # last transcript
    for k in ("device", "server", "prompt", "backdrop"):
        kill_tree(procs.get(k))
    meta.update(json.loads((take / "flash.json").read_text()))
    runs = sorted((ROOT / "evidence" / "runs").glob(f"*_{label}"))
    meta["capture_run"] = str(runs[-1]) if runs else None
    (take / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("take saved:", take)


if __name__ == "__main__":
    main()
