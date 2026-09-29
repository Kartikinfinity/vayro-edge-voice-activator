"""Live demo session for the video: runs the REAL ASR server and the REAL device console, shows a full-screen dashboard
that is driven only by their output lines (nothing simulated, every panel quotes a live line), screen-records it in real
time with ffmpeg, and keeps all raw logs of the take next to the video.

Modes
  demo        capture firmware (same model/pipeline as the product + USB microphone audio, so the video's sound is
              exactly what the device heard). On-screen prompts tell the speaker what to say.
  efficiency  product firmware (the judged configuration, no USB audio): live @MEM / @CPU lines while idle-listening.

Usage (host venv):  python host/demo_session.py --mode demo|efficiency [--no-record] [--wall-s 110]
Output: evidence/demo/<stamp>_<mode>/ {screen.mp4, server.log, device.log, events.jsonl, meta.json} + the capture run.
"""
import argparse
import datetime as dt
import json
import pathlib
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk

import imageio_ffmpeg

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv-host" / "Scripts" / "python.exe")
FF = imageio_ffmpeg.get_ffmpeg_exe()
ASR_MODEL = r"D:\ps26172_ext\vosk\vosk-model-en-in-0.5"
STATIC_DIRAM = 139695  # idf.py size of the final product build (evidence/final_product_size_v2b.log)

BG, PANEL, PANEL2, TXT, MUTED = "#0B1220", "#152033", "#1B2940", "#E6EDF7", "#8FA3BF"
ORANGE, GREEN, BLUE, RED = "#F59E0B", "#22C55E", "#38BDF8", "#F87171"
UI, UIB, MONO = ("Segoe UI", 14), ("Segoe UI Semibold", 14), ("Consolas", 11)

PROMPTS = [("Get ready \u2014 the board is listening", "", 6),
           ("Say:  \u201cHey Vayro \u2026 turn on the light\u201d", "1 / 5", 12),
           ("Say:  \u201cHey Vayro \u2026 what time is it\u201d", "2 / 5", 12),
           ("Say:  \u201cHey Vayro \u2026 play some music\u201d", "3 / 5", 12),
           ("Say:  \u201cHey Vayro \u2026 open the door\u201d", "4 / 5", 12),
           ("Say:  \u201cHey Vayro \u2026 set a timer for five minutes\u201d", "5 / 5", 12),
           ("Now talk normally \u2014 WITHOUT the keyword", "no keyword", 16),
           ("Done \u2014 thank you", "", 5)]


def now():
    return time.time()


class Proc:
    """Subprocess whose stdout lines are queued with the wall time they were read, and tee'd to a log file."""

    def __init__(self, name, cmd, log, q):
        self.name, self.q = name, q
        self.log = open(log, "w", encoding="utf-8")
        self.p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buf = b""
        while True:
            ch = self.p.stdout.read1(4096) if hasattr(self.p.stdout, "read1") else self.p.stdout.read(1)
            if not ch:
                break
            buf += ch
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                # the console rewrites its progress line with \r and device lines share that physical line:
                # every \r-separated segment is its own line (Windows also ends lines with \r\n)
                t = now()
                for seg in raw.decode("utf-8", "replace").split("\r"):
                    line = seg.rstrip()
                    if not line.strip():
                        continue
                    self.log.write(f"{t:.3f} {line}\n")
                    self.q.put((self.name, line, t))
                self.log.flush()
        self.q.put((self.name, None, now()))


class Dashboard:
    def __init__(self, args):
        self.args = args
        self.mode = args.mode
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out = ROOT / "evidence" / "demo" / f"{stamp}_{self.mode}"
        self.out.mkdir(parents=True, exist_ok=True)
        self.events = open(self.out / "events.jsonl", "w", encoding="utf-8")
        self.q = queue.Queue()
        self.dev_lines, self.srv_lines = [], []
        self.status = {"server": "starting", "wifi": "\u2014", "tcp": "\u2014", "boot": "", "kws": "", "mem": "",
                       "cpu": None, "stats": None, "mem_total": None, "heap_min_low": None}
        self.detections, self.acts = [], []
        self.pending_asr = None
        self.flash_until = 0
        self.kw_flash_until = 0
        self.prompt_t0 = None
        self.ended = False
        self.dev = self.srv = self.rec = None

        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg=BG)
        # abort only on Ctrl+Shift+Q (a stray Esc ended a take, 29 Sep 20:58)
        self.root.bind("<Control-Shift-Q>", lambda e: self.finish(force=True))
        self.W, self.H = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.c = tk.Canvas(self.root, width=self.W, height=self.H, bg=BG, highlightthickness=0)
        self.c.pack()
        self.meta = {"mode": self.mode, "screen": [self.W, self.H], "started": now()}
        self.root.after(300, self.start)
        self.root.after(50, self.tick)

    def ev(self, kind, **kw):
        kw.update(kind=kind, wall=round(now(), 3))
        self.events.write(json.dumps(kw) + "\n")
        self.events.flush()

    # ------------------------------------------------------------------ orchestration
    def start(self):
        srv_cmd = [PY, "-u", "server/ingest.py", "--port", "5005"]
        srv_cmd += (["--asr", ASR_MODEL, "--min-after-s", "0.8", "--stream-s-max", "6"] if self.mode == "demo"
                    else ["--stream-s", "3.0"])
        self.srv = Proc("srv", srv_cmd, self.out / "server.log", self.q)
        self.ev("server_started", cmd=srv_cmd)

    def start_recording_and_device(self):
        if not self.args.no_record:
            self.rec = subprocess.Popen([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab", "-framerate",
                                         "30", "-draw_mouse", "0", "-i", "desktop", "-c:v", "libx264", "-preset",
                                         "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(self.out / "screen.mp4")],
                                        stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            self.ev("recording_started")
        # sync marker: a 0.4 s white frame, its wall time logged (used to align the device audio in post)
        self.root.after(1500, self.sync_flash)
        label = f"demo_video_{self.mode}"
        note = ("Demo video take (demo mode): capture firmware v2b, speaker prompted on screen" if self.mode == "demo"
                else "Demo video take (efficiency mode): product firmware v2b, idle listening")
        cmd = [PY, "-u", "host/capture.py", "--port", "COM7", "--wall-s", str(self.args.wall_s), "--echo-stats", "--label", label,
               "--note", note]
        self.root.after(2600, lambda: self._start_dev(cmd))

    def _start_dev(self, cmd):
        self.dev = Proc("dev", cmd, self.out / "device.log", self.q)
        self.ev("device_console_started", cmd=cmd)

    def sync_flash(self):
        self.flash_until = now() + 0.4
        self.meta["sync_flash_wall"] = now()
        self.ev("sync_flash")

    def finish(self, force=False):
        if self.ended:
            return
        self.ended = True
        self.ev("finish", force=force)

        def stop():
            time.sleep(0 if force else 5)  # let the server finish the last transcript
            if self.rec and self.rec.poll() is None:
                try:
                    self.rec.stdin.write(b"q")
                    self.rec.stdin.flush()
                    self.rec.wait(15)
                except Exception:
                    self.rec.kill()
            for pr in (self.dev, self.srv):
                if pr and pr.p.poll() is None:
                    if pr is self.dev and not force:
                        try:
                            pr.p.wait(20)  # the console ends itself (--wall-s) and saves its run
                        except subprocess.TimeoutExpired:
                            pass
                    # the venv python.exe is a launcher with a child interpreter: kill the whole tree
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pr.p.pid)], capture_output=True)
            self.meta["ended"] = now()
            self.meta["detections"] = self.detections
            self.meta["activations"] = self.acts
            (self.out / "meta.json").write_text(json.dumps(self.meta, indent=2), encoding="utf-8")
            self.root.after(0, self.root.destroy)

        threading.Thread(target=stop, daemon=True).start()

    # ------------------------------------------------------------------ parsing
    def handle(self, who, line, t):
        if line is None:
            self.ev(f"{who}_exit")
            if who == "dev" and not self.ended:
                self.root.after(1000, self.finish)
            return
        (self.dev_lines if who == "dev" else self.srv_lines).append(line)
        if who == "srv":
            if "ingest listening" in line and self.status["server"] != "listening":
                self.status["server"] = "listening"
                self.ev("server_listening")
                self.start_recording_and_device()
            elif "device connected" in line:
                self.status["server"] = "device connected"
            m = re.search(r'ASR: "(.*?)"\s+\| after trigger: "(.*?)"\s+\(endpoint at (\S+) s after trigger by (\S+)\)',
                          line)
            if m:
                self.pending_asr = {"transcript": m.group(1), "after": m.group(2), "endpoint_s": m.group(3),
                                    "by": m.group(4)}
            m = re.search(r"activation (\d+): ([\d.]+) s audio, L1_start ([\d.]+|None) ms, L1_audio0 ([\d.]+|None) ms"
                          r".*end=(\S+), overrun=(\S+), seq_gaps=(\d+)", line)
            if m:
                a = {"act": int(m.group(1)), "audio_s": float(m.group(2)), "l1_start": m.group(3),
                     "l1_audio0": m.group(4), "end": m.group(5).rstrip(","), "overrun": m.group(6).rstrip(","),
                     "seq_gaps": int(m.group(7)), "wall": t}
                if self.pending_asr:
                    a.update(self.pending_asr)
                    self.pending_asr = None
                self.acts.append(a)
                self.ev("activation", **a)
            return
        m = re.search(r"@(\w+)(.*)", line)
        if not m:
            return
        tag, rest = m.group(1), m.group(2)
        kv = dict(re.findall(r"(\w+)=(\S+)", rest))
        if tag == "BOOT":
            self.status["boot"] = f"ESP-IDF {kv.get('idf', '?')} \u00b7 {kv.get('cpu_mhz', '?')} MHz \u00b7 PSRAM " \
                                  f"{'off' if kv.get('emb_psram') == '0' else kv.get('emb_psram')}"
        elif tag == "KWS":
            self.status["kws"] = (f"model {kv.get('run')} \u00b7 {kv.get('model_bytes')} B int8 \u00b7 arena "
                                  f"{kv.get('arena_used')} B \u00b7 threshold 0.{kv.get('thr_pct')}")
        elif tag == "NET":
            if "wifi" in kv:
                self.status["wifi"] = kv["wifi"]
            if "tcp" in kv:
                self.status["tcp"] = kv["tcp"]
                if kv["tcp"] == "connected" and self.prompt_t0 is None and self.mode == "demo":
                    self.prompt_t0 = t + 3.0
                    self.ev("prompts_scheduled", t0=self.prompt_t0)
        elif tag == "MEM":
            self.status["mem"] = rest.strip()
            if "int_total" in kv:
                self.status["mem_total"] = int(kv["int_total"])
        elif tag == "CPU":
            self.status["cpu"] = kv
            self.ev("cpu", **kv)
        elif tag == "STATS":
            self.status["stats"] = kv
            hm = int(kv.get("heap_min", 0) or 0)
            if hm and (self.status["heap_min_low"] is None or hm < self.status["heap_min_low"]):
                self.status["heap_min_low"] = hm
        elif tag == "KW" and "synthetic" not in kv:
            d = {"t_ms": int(kv.get("t_ms", 0)), "p": float(kv.get("p", 0)), "avg": float(kv.get("avg", 0)),
                 "streamed": kv.get("streamed"), "wall": t}
            self.detections.append(d)
            self.kw_flash_until = t + 2.5
            self.ev("kw", **d)

    # ------------------------------------------------------------------ drawing
    def tick(self):
        while True:
            try:
                who, line, t = self.q.get_nowait()
            except queue.Empty:
                break
            self.handle(who, line, t)
        self.draw()
        if self.prompt_t0 is not None and not self.ended:
            total = sum(p[2] for p in PROMPTS)
            if now() > self.prompt_t0 + total + 2 and self.mode == "demo":
                self.finish()
        self.root.after(50, self.tick)

    def panel(self, x, y, w, h, fill=PANEL):
        r = 14
        c = self.c
        c.create_rectangle(x + r, y, x + w - r, y + h, fill=fill, outline=fill)
        c.create_rectangle(x, y + r, x + w, y + h - r, fill=fill, outline=fill)
        for (cx, cy) in ((x, y), (x + w - 2 * r, y), (x, y + h - 2 * r), (x + w - 2 * r, y + h - 2 * r)):
            c.create_oval(cx, cy, cx + 2 * r, cy + 2 * r, fill=fill, outline=fill)

    def txt(self, x, y, s, font=UI, fill=TXT, anchor="nw", width=None):
        kw = {"width": width} if width else {}
        self.c.create_text(x, y, text=s, font=font, fill=fill, anchor=anchor, **kw)

    def draw(self):
        c, W, H, T = self.c, self.W, self.H, now()
        c.delete("all")
        if T < self.flash_until:
            c.create_rectangle(0, 0, W, H, fill="#FFFFFF", outline="#FFFFFF")
            return
        # header
        self.txt(28, 18, "Hey Vayro \u2014 live on the physical prototype", ("Segoe UI Semibold", 24))
        self.txt(30, 60, "SIH 2026 \u00b7 PS 26172 \u00b7 ESP32-S3 + INMP441 microphone \u00b7 every value on this screen is "
                 "a live line from the device or the ASR server", ("Segoe UI", 12), MUTED)
        clock = dt.datetime.now().strftime("%H:%M:%S.%f")[:-4]
        self.panel(W - 300, 16, 272, 62, PANEL2)
        self.txt(W - 164, 26, clock, ("Consolas", 22, "bold"), TXT, "n")
        self.txt(W - 164, 58, "REAL TIME \u00b7 wall clock", ("Segoe UI", 9), GREEN, "n")
        # status chips
        chips = [("server", self.status["server"]), ("Wi-Fi", self.status["wifi"]), ("TCP", self.status["tcp"])]
        x = 30
        for k, v in chips:
            ok = v in ("listening", "device connected", "up", "connected")
            label = f"{k}: {v}"
            wpx = 12 + 8 * len(label)
            self.panel(x, 92, wpx, 30, PANEL2)
            self.txt(x + 12, 98, label, ("Segoe UI", 11), GREEN if ok else ORANGE)
            x += wpx + 10
        if self.status["kws"]:
            self.txt(x + 6, 98, self.status["kws"], ("Segoe UI", 11), MUTED)
        LW = int(W * 0.60)
        # prompt panel
        self.panel(28, 136, LW - 28, 118)
        if self.mode == "demo":
            if self.prompt_t0 is None:
                self.txt(52, 152, "Waiting for the board to boot and connect\u2026", ("Segoe UI Semibold", 22), MUTED)
                self.txt(52, 202, "the board is reset by the console; prompts start 3 s after TCP connects",
                         ("Segoe UI", 12), MUTED)
            else:
                el = T - self.prompt_t0
                acc, cur, nxt = 0, None, None
                for k, p in enumerate(PROMPTS):
                    if acc <= el < acc + p[2]:
                        cur, left, nxt = p, acc + p[2] - el, PROMPTS[k + 1] if k + 1 < len(PROMPTS) else None
                        break
                    acc += p[2]
                if el < 0:
                    self.txt(52, 160, f"Starting in {-el:.0f} s \u2026", ("Segoe UI Semibold", 26), MUTED)
                elif cur:
                    self.txt(52, 150, cur[0], ("Segoe UI Semibold", 28), ORANGE if "Say" in cur[0] else TXT)
                    self.txt(LW - 24, 152, cur[1], ("Segoe UI", 13), MUTED, "ne")
                    frac = max(0.0, min(1.0, left / cur[2]))
                    c.create_rectangle(52, 214, 52 + int((LW - 104) * frac), 220, fill=BLUE, outline=BLUE)
                    if nxt:
                        self.txt(52, 228, f"next: {nxt[0]}", ("Segoe UI", 11), MUTED)
                else:
                    self.txt(52, 160, "Take complete", ("Segoe UI Semibold", 26), GREEN)
        else:
            self.txt(52, 150, "Product firmware \u2014 idle, continuous listening", ("Segoe UI Semibold", 26), TXT)
            self.txt(52, 200, "the judged configuration (no USB audio): live memory and CPU lines below",
                     ("Segoe UI", 13), MUTED)
        # detection panel
        y0 = 268
        self.panel(28, y0, LW - 28, 170, PANEL)
        if T < self.kw_flash_until and self.detections:
            d = self.detections[-1]
            self.panel(28, y0, LW - 28, 170, "#0F3D24")
            self.txt(52, y0 + 18, "KEYWORD DETECTED ON THE DEVICE", ("Segoe UI Semibold", 30), GREEN)
            self.txt(52, y0 + 76, f"score {d['p']:.3f} \u00b7 mean of last 3 = {d['avg']:.3f} (threshold 0.80) \u00b7 "
                     f"device time {d['t_ms'] / 1000:.2f} s", ("Segoe UI", 15), TXT)
            self.txt(52, y0 + 110, "\u2192 streaming the 571 ms pre-roll + live audio to the ASR server"
                     if d.get("streamed") == "1" else "(stream busy \u2014 not streamed)", ("Segoe UI", 13), BLUE)
        else:
            self.txt(52, y0 + 18, "Listening on the device\u2026", ("Segoe UI Semibold", 26), TXT)
            st = self.status["stats"]
            lvl = float(st.get("level_dbfs", -90)) if st else -90.0
            self.txt(52, y0 + 70, f"microphone level {lvl:5.1f} dBFS (device @STATS, 1 Hz)", ("Segoe UI", 12), MUTED)
            frac = max(0.0, min(1.0, (lvl + 70) / 60))
            c.create_rectangle(52, y0 + 98, LW - 52, y0 + 112, fill=PANEL2, outline=PANEL2)
            c.create_rectangle(52, y0 + 98, 52 + int((LW - 104) * frac), y0 + 112, fill=BLUE, outline=BLUE)
            self.txt(52, y0 + 126, f"keyword detections so far: {len(self.detections)}", ("Segoe UI", 13), MUTED)
        # activations / transcripts or efficiency
        y1 = 452
        self.panel(28, y1, LW - 28, H - y1 - 24, PANEL)
        if self.mode == "demo":
            self.txt(52, y1 + 14, "ASR server \u2014 streams received after the keyword", ("Segoe UI Semibold", 17))
            yy = y1 + 52
            for a in reversed(self.acts[-4:]):
                self.txt(52, yy, f"#{a['act']}", ("Segoe UI Semibold", 18), BLUE)
                # only the words AFTER the keyword (the pre-roll holds the keyword itself, which the ASR mis-hears)
                tr = a.get("after") or ""
                self.txt(110, yy - 2, f"\u201c{tr}\u201d" if tr else "(no command after the keyword)",
                         ("Segoe UI Semibold", 19), TXT if tr else MUTED)
                by = {"vad_trailing_silence": "end of speech (VAD)", "vad_no_speech": "no speech (VAD)",
                      "cap": "6 s cap", "asr": "ASR endpoint"}.get(a.get("by"), a.get("by", "?"))
                self.txt(110, yy + 32, f"first audio at server +{a['l1_audio0']} ms after detection \u00b7 stream ended: "
                         f"{by} \u00b7 packets lost {a['seq_gaps']} \u00b7 overrun "
                         f"{'no' if a['overrun'] == 'False' else 'YES'}", ("Segoe UI", 11), MUTED)
                yy += 70
            if not self.acts:
                self.txt(52, yy, "no stream yet \u2014 audio leaves the device only after the keyword",
                         ("Segoe UI", 14), MUTED)
            self.txt(52, H - 62, "Demo build = final firmware (model v2b) + a USB stream of the microphone, so the video "
                     "carries exactly what the device heard. RAM / CPU are shown separately on the product build.",
                     ("Segoe UI", 10), MUTED, width=LW - 110)
        else:
            self.txt(52, y1 + 14, "Efficiency \u2014 live from the device", ("Segoe UI Semibold", 17))
            cpu = self.status["cpu"]
            tot, low = self.status["mem_total"], self.status["heap_min_low"]
            big = [("idle CPU, busiest core", f"{float(cpu['core1_busy']):.2f} %" if cpu else "\u2026"),
                   ("idle CPU, other core", f"{float(cpu['core0_busy']):.2f} %" if cpu else "\u2026"),
                   ("RAM now (static + peak heap)",
                    f"{(STATIC_DIRAM + tot - low) / 1024:.1f} KiB" if tot and low else "\u2026")]
            bx = 52
            bw = (LW - 28 - 48 - 2 * 16) // 3
            for lab, val in big:
                self.panel(bx, y1 + 56, bw, 140, PANEL2)
                self.txt(bx + bw // 2, y1 + 78, val, ("Segoe UI Semibold", 30), ORANGE, "n")
                self.txt(bx + bw // 2, y1 + 140, lab, ("Segoe UI", 12), MUTED, "n")
                bx += bw + 16
            self.txt(52, y1 + 214, "CPU from FreeRTOS run-time stats (@CPU, 10 s windows). RAM = static DIRAM "
                     f"{STATIC_DIRAM:,} B (linker report of this build) + heap in use at its lowest point (@MEM total "
                     "\u2212 @STATS heap_min). Limits in the PS: < 256 KB RAM, < 10 % CPU.", ("Segoe UI", 11), MUTED,
                     width=LW - 110)
        # raw logs
        RX = LW + 16
        self.panel(RX, 136, W - RX - 28, (H - 160) // 2 - 8, PANEL)
        self.txt(RX + 18, 146, "device console (USB) \u2014 raw lines", ("Segoe UI Semibold", 12), MUTED)
        self.raw(RX + 18, 172, self.dev_lines, 16, W - RX - 64)
        ry = 136 + (H - 160) // 2 + 8
        self.panel(RX, ry, W - RX - 28, (H - 160) // 2 - 8, PANEL)
        self.txt(RX + 18, ry + 10, "ASR server \u2014 raw lines", ("Segoe UI Semibold", 12), MUTED)
        self.raw(RX + 18, ry + 36, self.srv_lines, 16, W - RX - 64)

    def raw(self, x, y, lines, n, wpx):
        # high-rate status lines (1 Hz @STATS/@PERF) stay in the saved logs but would flood this small panel
        keep = [l for l in lines if not l.strip().startswith(("recorded", "@STATS", "@PERF"))][-n:]
        maxc = max(20, wpx // 8)
        for k, l in enumerate(keep):
            s = l.strip()
            col = GREEN if "@KW" in s or "ASR:" in s else (BLUE if "@STREAM" in s or "activation" in s else TXT)
            self.txt(x, y + k * 21, s[:maxc] + ("\u2026" if len(s) > maxc else ""), MONO, col)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["demo", "efficiency"], default="demo")
    ap.add_argument("--wall-s", type=int, default=0, help="device console duration (default: demo 118, efficiency 75)")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()
    if not args.wall_s:
        args.wall_s = 118 if args.mode == "demo" else 75
    d = Dashboard(args)
    d.root.mainloop()
    print("take saved in", d.out)


if __name__ == "__main__":
    main()
