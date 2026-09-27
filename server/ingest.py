"""PS26172 ingest server (M5): receives keyword-triggered audio streams from the ESP32-S3 over one warm TCP
connection, timestamps every packet (IN-5), answers clock pings (IN-6), ends streams (endpointing), and writes
one WAV + JSON per activation plus activations.csv.

Clock: all server timestamps are time.perf_counter_ns() in µs (monotonic). The device reports
offset = server_us - device_us from the lowest-RTT recent ping, so device times convert to server time.

Latency (architecture §10.2):
  L1_start  = t_rx(START packet)       - (t_detect_device + offset)
  L1_audio0 = t_rx(first audio packet) - (t_detect_device + offset)
L2 (keyword acoustic end -> server) is derived offline from the streamed audio (see server/latency_report.py).

Endpointing (M5): the server sends END once `--stream-s` seconds of audio AFTER the trigger have arrived.
M6 replaces this with the ASR's own endpoint (server/asr.py).

Usage (host venv): python server/ingest.py --port 5005 [--stream-s 3.0]
"""
import argparse
import csv
import datetime as dt
import json
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


class Session:
    def __init__(self, conn, out, args):
        self.conn, self.out, self.args = conn, out, args
        self.offset_us, self.rtt_us, self.pings = None, None, 0
        self.act = None
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
            if not a["end_sent"] and after_trigger_s >= self.args.stream_s:
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
        with wave.open(str(self.out / f"{stem}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm)
        (self.out / f"{stem}.json").write_text(json.dumps(a, indent=2), encoding="utf-8")
        new = not (self.out / "activations.csv").exists()
        with open(self.out / "activations.csv", "a", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(a))
            if new:
                wr.writeheader()
            wr.writerow(a)
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
    ap.add_argument("--stream-s", type=float, default=3.0, help="seconds of audio after the trigger before END")
    args = ap.parse_args()
    out = ROOT / "evidence" / "server" / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "server_config.json").write_text(json.dumps(vars(args), indent=2), encoding="utf-8")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"ingest listening on 0.0.0.0:{args.port}; writing to {out}", flush=True)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=serve, args=(conn, addr, out, args), daemon=True).start()


if __name__ == "__main__":
    main()
