"""PS26172 ingest server (M5): receives keyword-triggered audio streams from the ESP32-S3 over one warm TCP
connection, timestamps every packet (IN-5), answers clock pings (IN-6), ends streams (endpointing), and writes
one WAV + JSON per activation plus activations.csv.

Clock: all server timestamps are time.perf_counter_ns() in µs (monotonic). The device reports
offset = server_us - device_us from the lowest-RTT recent ping, so device times convert to server time.

Latency (architecture §10.2):
  L1_start  = t_rx(START packet)       - (t_detect_device + offset)
  L1_audio0 = t_rx(first audio packet) - (t_detect_device + offset)
L2 (keyword acoustic end -> server) is derived offline from the streamed audio (see server/latency_report.py).

Endpointing: M5 (no --asr) sends END once `--stream-s` s of audio AFTER the trigger have arrived. M6 (--asr) ends on
the server VAD (VadEndpointer, default) or on the Vosk utterance endpoint (--endpoint asr), with a hard cap.

Usage (host venv): python server/ingest.py --port 5005 [--stream-s 3.0]
"""
import argparse
import csv
import datetime as dt
import json
import math
import pathlib
import socket
import struct
import threading
import time
import wave

MAGIC = 0xA7
F_START, F_CONT, F_END, F_OVERRUN, F_PING, F_INFO, F_PONG = 0x01, 0x02, 0x04, 0x08, 0x20, 0x40, 0x80
PAYLOAD = {F_START: 32, F_CONT: 1280, F_END: 16, F_OVERRUN: 0, F_PING: 8, F_INFO: 16}
HDR = 8
ROOT = pathlib.Path(__file__).resolve().parents[1]


def now_us():
    return time.perf_counter_ns() // 1000


ASR_MODEL = None  # vosk.Model, loaded once when --asr is given (M6)
ASR_GRAMMAR = None  # optional JSON phrase list (--grammar)


def new_recognizer():
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(ASR_MODEL, 16000, ASR_GRAMMAR) if ASR_GRAMMAR else KaldiRecognizer(ASR_MODEL, 16000)
    rec.SetWords(True)
    return rec


class AsrFrontEnd:
    """ASR-side conditioning of the device stream (M6 finding: raw device audio at about -40 dBFS speech with 60-70 Hz
    fan rumble at about -30 dBFS decoded to nothing; a steep 150 Hz high-pass + gain restored a LibriSpeech control
    at device level). The KWS path on the device is unaffected — this runs on the server only.

    Gain is keyword-referenced and fixed per stream (M6 run 20260928_192727: the earlier block AGC moved the gain
    inside words and made transcripts flip with small level changes). The pre-roll ends at the detected keyword, so
    its loudest part is the same speaker at the same distance just before the command: gain = speech at -20 dBFS
    (p95 of 50 ms 300-4000 Hz RMS, the asr_level_test convention). The pre-roll arrives as one burst from the device
    ring, so holding it back until the gain is known adds no measurable delay."""

    def __init__(self, preroll_samples):
        import numpy as np
        from scipy import signal
        self.np, self.signal = np, signal
        self.sos = signal.butter(8, 150, btype="high", fs=16000, output="sos")
        self.sos_sp = signal.butter(4, [300, 4000], btype="band", fs=16000, output="sos")
        self.zi = signal.sosfilt_zi(self.sos) * 0.0
        self.need = preroll_samples
        self.held = []
        self.gain = None
        self.speech_dbfs = None

    def _set_gain(self, y):
        np = self.np
        sp = self.signal.sosfilt(self.sos_sp, y)
        n = len(sp) // 800
        if n == 0:
            self.gain = 1.0
            return
        lev = np.sqrt(np.mean(sp[: n * 800].reshape(n, 800) ** 2, axis=1))
        rms = max(float(np.percentile(lev, 95)), 1.0)
        self.speech_dbfs = round(20 * np.log10(rms * np.sqrt(2) / 32768), 1)
        self.gain = float(np.clip(10 ** (-20 / 20) * 32768 / np.sqrt(2) / rms, 0.5, 40.0))

    def __call__(self, pcm_bytes):
        np = self.np
        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float64)
        y, self.zi = self.signal.sosfilt(self.sos, x, zi=self.zi)
        if self.gain is None:
            self.held.append(y)
            if sum(len(h) for h in self.held) < self.need:
                return b""
            y = np.concatenate(self.held)
            self.held = []
            self._set_gain(y[: self.need])
        return np.clip(np.round(y * self.gain), -32768, 32767).astype(np.int16).tobytes()


class VadEndpointer:
    """Server-side utterance endpointing on the raw stream (architecture §9.5 names WebRTC-VAD; this is an energy VAD
    in the speech band so no extra package is needed — a recorded deviation). Why not the ASR's endpoint: in run
    20260928_192727 the decoder's real-time path heard most commands as noise, so Vosk only endpointed on its 5 s
    rule and the long streams hid the next keywords from the device.
    Rule (fixed before evaluation): 20 ms frames, 300-4000 Hz level; threshold = keyword level in the pre-roll
    (p95 of 50 ms frames) - 20 dB, not below -60 dBFS; speech onset = 3 consecutive frames above it after the
    trigger; END after `hang_s` of trailing non-speech, or at `idle_s` if no speech started; the caller caps it."""

    def __init__(self, preroll_samples, hang_s=0.7, idle_s=1.5):
        import numpy as np
        from scipy import signal
        self.np, self.signal = np, signal
        self.sos = signal.butter(4, [300, 4000], btype="band", fs=16000, output="sos")
        self.zi = signal.sosfilt_zi(self.sos) * 0.0
        self.pre = preroll_samples
        self.hang, self.idle = int(hang_s * 50), int(idle_s * 50)
        self.buf = np.zeros(0)
        self.seen = 0
        self.thr = None
        self.kw_dbfs = None
        self.run = 0
        self.speech = False
        self.trailing = 0
        self.post_frames = 0
        self.reason = None

    def _db(self, v):
        return 20 * self.np.log10(max(float(v), 1.0) * self.np.sqrt(2) / 32768)

    def __call__(self, pcm_bytes):
        """Feed raw int16 bytes; returns True once the utterance has ended."""
        np = self.np
        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float64)
        y, self.zi = self.signal.sosfilt(self.sos, x, zi=self.zi)
        self.buf = np.concatenate([self.buf, y])
        if self.thr is None:
            if len(self.buf) < self.pre:
                return False
            p = self.buf[: self.pre]
            n = len(p) // 800
            lev = np.sqrt(np.mean(p[: n * 800].reshape(n, 800) ** 2, axis=1)) if n else np.ones(1)
            self.kw_dbfs = round(self._db(np.percentile(lev, 95)), 1)
            self.thr = max(self.kw_dbfs - 20.0, -60.0)
            self.buf = self.buf[self.pre:]
        done = False
        while len(self.buf) >= 320:
            f, self.buf = self.buf[:320], self.buf[320:]
            self.post_frames += 1
            loud = self._db(np.sqrt(np.mean(f ** 2))) >= self.thr
            self.run = self.run + 1 if loud else 0
            if not self.speech:
                if self.run >= 3:
                    self.speech, self.trailing = True, 0
                elif self.post_frames >= self.idle:
                    done, self.reason = True, "no_speech"
            else:
                self.trailing = 0 if loud else self.trailing + 1
                if self.trailing >= self.hang:
                    done, self.reason = True, "trailing_silence"
        return done


class Session:
    def __init__(self, conn, out, args):
        self.conn, self.out, self.args = conn, out, args
        self.offset_us, self.rtt_us, self.pings = None, None, 0
        self.act = None
        self.rec = None
        # Pre-created so that START handling never blocks the receive loop (creating a recognizer took ~190 ms and
        # inflated L1_audio0 in run 20260928_175052).
        self.next_rec = new_recognizer() if ASR_MODEL is not None else None
        self.asr_fe = None
        self.vad = None
        self.tx_lock = threading.Lock()
        self.conn_stamp = dt.datetime.now().strftime("c%H%M%S")

    def send(self, flags, payload=b""):
        hdr = bytes([MAGIC, flags, 0, 0, 0, 0, 0, 0])
        with self.tx_lock:
            self.conn.sendall(hdr + payload)

    def on_packet(self, flags, seq, payload, t_rx):
        if flags == F_PING:
            (t1,) = struct.unpack("<Q", payload)
            self.send(F_PONG, struct.pack("<QQQ", t1, t_rx, now_us()))
        elif flags == F_INFO:
            self.offset_us, self.rtt_us, self.pings = struct.unpack("<qII", payload)
        elif flags == F_START:
            act, kw_frame, t_det, pre_ms, first, raw = struct.unpack("<IIQIIb", payload[:25])
            self.act = {"activation": act, "kw_frame": kw_frame, "t_detect_device_us": t_det, "preroll_ms": pre_ms,
                        "first_sample": first, "raw_posterior": raw, "t_start_rx_us": t_rx, "t_audio0_rx_us": None,
                        "offset_us": self.offset_us, "rtt_us": self.rtt_us, "pings": self.pings,
                        "pcm": bytearray(), "packets": 0, "seq_gaps": 0, "last_seq": 0, "end_sent": False,
                        "overrun": False, "wall_time": dt.datetime.now().isoformat(timespec="milliseconds")}
            if ASR_MODEL is not None:
                self.rec, self.next_rec = self.next_rec, None
                self.asr_fe = AsrFrontEnd(pre_ms * 16)
                self.vad = VadEndpointer(pre_ms * 16) if self.args.endpoint == "vad" else None
                self.act["asr_endpoint_at_s"] = None
                self.act["endpoint_by"] = None
        elif flags == F_CONT and self.act:
            a = self.act
            if a["t_audio0_rx_us"] is None:
                a["t_audio0_rx_us"] = t_rx
            if a["last_seq"] and seq != (a["last_seq"] + 1) & 0xFFFF:
                a["seq_gaps"] += 1
            a["last_seq"] = seq
            a["pcm"] += payload
            a["packets"] += 1
            after_trigger_s = len(a["pcm"]) / 2 / 16000 - a["preroll_ms"] / 1000
            end_now = False
            if self.rec is not None:
                # M6 endpointing (--endpoint): the VAD (default) or Vosk's own utterance endpoint -> END, once at
                # least --min-after-s of post-trigger audio has arrived; hard cap --stream-s-max.
                blk = self.asr_fe(payload)
                a.setdefault("asr_pcm", bytearray()).extend(blk)
                ended_by = None
                if blk and self.rec.AcceptWaveform(blk):
                    seg = json.loads(self.rec.Result())
                    a.setdefault("asr_segments", []).append(seg)
                    if self.vad is None:
                        ended_by = "asr"
                if self.vad is not None and self.vad(payload):
                    ended_by = "vad_" + self.vad.reason
                if ended_by and after_trigger_s >= self.args.min_after_s and a["asr_endpoint_at_s"] is None:
                    a["asr_endpoint_at_s"] = round(after_trigger_s, 3)
                    a["endpoint_by"] = ended_by
                    end_now = True
                if after_trigger_s >= self.args.stream_s_max and a["endpoint_by"] is None:
                    a["endpoint_by"] = "cap"
                end_now = end_now or after_trigger_s >= self.args.stream_s_max
            else:
                end_now = after_trigger_s >= self.args.stream_s
            if not a["end_sent"] and end_now:
                self.send(F_END, struct.pack("<I", a["activation"]))
                a["end_sent"] = True
                a["t_end_sent_us"] = now_us()
        elif flags == F_OVERRUN and self.act:
            self.act["overrun"] = True
        elif flags == F_END and self.act:
            act, sent, min_slack, reason = struct.unpack("<IIII", payload)
            self.finish(dict(device_samples_sent=sent, device_min_slack_ms=min_slack / 16,
                             device_end_reason={0: "none", 1: "server_end", 2: "device_timeout", 3: "overrun",
                                                4: "socket_error"}.get(reason, reason), t_end_rx_us=t_rx))

    def finish(self, extra):
        a = self.act
        self.act = None
        a.update(extra)
        if self.rec is not None:
            t0 = now_us()
            segs = a.pop("asr_segments", []) + [json.loads(self.rec.FinalResult())]
            words = [w for s in segs for w in s.get("result", [])]
            pre = a["preroll_ms"] / 1000
            a["asr_transcript"] = " ".join(w["word"] for w in words)
            # Words starting inside the pre-roll carry the keyword; the rest is the "subsequent audio" (AMB-13).
            a["asr_after_trigger"] = " ".join(w["word"] for w in words if w["start"] >= pre - 0.15)
            a["asr_words"] = words
            a["asr_final_latency_ms"] = round((now_us() - t0) / 1000, 2)
            a["asr_conditioning"] = "8th-order 150 Hz high-pass + fixed keyword-referenced gain (pre-roll speech -> -20 dBFS)"
            if self.vad is not None:
                a["vad_kw_dbfs"], a["vad_thr_dbfs"] = self.vad.kw_dbfs, self.vad.thr
            a["asr_preroll_speech_dbfs"] = self.asr_fe.speech_dbfs
            a["asr_gain_db"] = round(20 * math.log10(self.asr_fe.gain), 1) if self.asr_fe.gain else None
            a["asr_grammar"] = bool(ASR_GRAMMAR)
            self.rec = None
            self.next_rec = new_recognizer()  # ready before the next START
        pcm = bytes(a.pop("pcm"))
        a["audio_seconds"] = round(len(pcm) / 2 / 16000, 3)
        if a["offset_us"] is not None:
            t_det_srv = a["t_detect_device_us"] + a["offset_us"]
            a["L1_start_ms"] = round((a["t_start_rx_us"] - t_det_srv) / 1000, 3)
            a["L1_audio0_ms"] = round((a["t_audio0_rx_us"] - t_det_srv) / 1000, 3) if a["t_audio0_rx_us"] else None
            a["clock_uncertainty_ms_half_rtt"] = round(a["rtt_us"] / 2000, 3)
        # Connection timestamp in the name: the device restarts activation numbering at 1 after every reboot, and
        # plain act0001.wav names overwrote earlier activations (session 20260927_192112, 19:30-19:52 files lost).
        stem = f"{self.conn_stamp}_act{a['activation']:04d}"
        a["file_stem"] = stem
        asr_pcm = bytes(a.pop("asr_pcm", b""))
        # <stem>.wav is the raw device stream (bit-exact, integrity checks); <stem>_asr.wav is what the ASR heard
        # (high-pass + keyword-referenced gain) — audible for playback, since raw speech sits at about -30..-40 dBFS.
        for name, data in ((f"{stem}.wav", pcm), (f"{stem}_asr.wav", asr_pcm)):
            if not data:
                continue
            with wave.open(str(self.out / name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(data)
        (self.out / f"{stem}.json").write_text(json.dumps(a, indent=2), encoding="utf-8")
        new = not (self.out / "activations.csv").exists()
        with open(self.out / "activations.csv", "a", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(a))
            if new:
                wr.writeheader()
            wr.writerow(a)
        if "asr_transcript" in a:
            print(f"    ASR: \"{a['asr_transcript']}\"  | after trigger: \"{a['asr_after_trigger']}\"  "
                  f"(endpoint at {a['asr_endpoint_at_s']} s after trigger by {a.get('endpoint_by')})", flush=True)
        print(f"[{a['wall_time']}] activation {a['activation']}: {a['audio_seconds']} s audio, "
              f"L1_start {a.get('L1_start_ms')} ms, L1_audio0 {a.get('L1_audio0_ms')} ms "
              f"(±{a.get('clock_uncertainty_ms_half_rtt')} ms clock), end={a['device_end_reason']}, "
              f"overrun={a['overrun']}, seq_gaps={a['seq_gaps']} -> {stem}.wav", flush=True)


def serve(conn, addr, out, args):
    print(f"device connected from {addr[0]}:{addr[1]}", flush=True)
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s = Session(conn, out, args)
    buf = bytearray()
    try:
        while True:
            chunk = conn.recv(65536)
            t_rx = now_us()
            if not chunk:
                break
            buf += chunk
            while len(buf) >= HDR:
                if buf[0] != MAGIC:
                    del buf[:1]
                    continue
                flags = buf[1]
                n = PAYLOAD.get(flags)
                if n is None:
                    del buf[:1]
                    continue
                if len(buf) < HDR + n:
                    break
                seq = buf[3] | (buf[4] << 8)
                s.on_packet(flags, seq, bytes(buf[HDR:HDR + n]), t_rx)
                del buf[:HDR + n]
    except (ConnectionResetError, OSError) as e:
        print(f"connection error: {e}", flush=True)
    print("device disconnected", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--stream-s", type=float, default=3.0, help="without --asr: seconds after the trigger before END")
    ap.add_argument("--asr", default="", help="Vosk model directory: enables M6 ASR + ASR endpointing")
    ap.add_argument("--min-after-s", type=float, default=0.5, help="with --asr: minimum post-trigger audio before END")
    ap.add_argument("--stream-s-max", type=float, default=6.0, help="with --asr: hard cap after the trigger")
    ap.add_argument("--grammar", default="", help="with --asr: JSON phrase list restricting recognition (e.g. server/commands.json)")
    ap.add_argument("--endpoint", choices=["vad", "asr"], default="vad",
                    help="with --asr: END on the server VAD (default) or on the Vosk utterance endpoint")
    args = ap.parse_args()
    if args.asr:
        global ASR_MODEL, ASR_GRAMMAR
        if args.grammar:
            ASR_GRAMMAR = pathlib.Path(args.grammar).read_text(encoding="utf-8")
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        t0 = time.time()
        ASR_MODEL = Model(args.asr)
        AsrFrontEnd(160)(b"\0" * 320)  # imports numpy/scipy now: the first START of run 20260928_192727 paid ~25 ms
        print(f"ASR model loaded from {args.asr} in {time.time() - t0:.1f} s", flush=True)
    out = ROOT / "evidence" / "server" / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "server_config.json").write_text(json.dumps(vars(args), indent=2), encoding="utf-8")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    srv.settimeout(1.0)  # accept() otherwise blocks Ctrl+C on Windows (a stuck server once shared port 5005)
    print(f"ingest listening on 0.0.0.0:{args.port}; writing to {out}", flush=True)
    try:
        while True:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            conn.settimeout(None)
            threading.Thread(target=serve, args=(conn, addr, out, args), daemon=True).start()
    except KeyboardInterrupt:
        print("ingest stopped", flush=True)


if __name__ == "__main__":
    main()
