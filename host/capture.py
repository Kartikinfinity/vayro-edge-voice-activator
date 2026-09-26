"""Record audio + device telemetry from the ESP32-S3 over the serial_link framing.

Writes one run folder (audio is streamed to disk, so multi-hour ambient recordings are safe):
  audio_24bit.wav        mono 16 kHz, 24-bit — exactly the INMP441 sample (I2S word >> 8)
  audio_16bit.wav        mono 16 kHz, int16 = int24 >> 8 — bit-identical to the device's int16 path
  device_log.txt         every TEXT frame, prefixed with host time (s since start)
  device_events.jsonl    parsed @BOOT/@CFG/@MEM/@DIAG/@STATS lines
  boot_raw.txt           non-frame bytes (ROM / bootloader output)
  capture_summary.json   integrity accounting: gaps, CRC errors, device drop counters
If the device reboots mid-run, later audio goes to audio_*_s2.wav etc. and is reported.

Usage:
  python host/capture.py --seconds 20 --label m1_sessionA [--port COM5] [--reset] [--note "..."]
"""
import argparse
import binascii
import datetime as dt
import json
import pathlib
import struct
import sys
import time
import wave

import serial
from serial.tools import list_ports

SYNC = b"\xA5\x5A\x26\x17"
T_AUDIO, T_TEXT = 1, 2
HDR, CRC_LEN, MAX_PAYLOAD = 8, 2, 1024
ESP_VIDS = {0x303A: "Espressif native USB-Serial-JTAG", 0x10C4: "Silicon Labs CP210x",
            0x1A86: "WCH CH34x", 0x0403: "FTDI"}
ROOT = pathlib.Path(__file__).resolve().parents[1]


def crc16_ccitt(data: bytes) -> int:
    # CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection) — same as the firmware.
    return binascii.crc_hqx(data, 0xFFFF)


def find_port():
    hits = [p for p in list_ports.comports() if p.vid in ESP_VIDS]
    if len(hits) != 1:
        found = ", ".join(f"{p.device} ({p.description}, VID={p.vid})" for p in list_ports.comports())
        sys.exit(f"Expected exactly one ESP32 serial port, found: {found or 'none'}. Use --port.")
    return hits[0].device, ESP_VIDS[hits[0].vid]


def parse_kv(line: str):
    tag, _, rest = line.strip().partition(" ")
    rec = {"type": tag[1:]}
    for tok in rest.split():
        k, _, v = tok.partition("=")
        try:
            rec[k] = int(v)
        except ValueError:
            try:
                rec[k] = float(v)
            except ValueError:
                rec[k] = v
    return rec


def to_int16_bytes(pcm24: bytes) -> bytes:
    # int16 = int24 >> 8 (arithmetic) == I2S 32-bit word >> 16: the top two bytes of each sample.
    out = bytearray(len(pcm24) // 3 * 2)
    out[0::2] = pcm24[1::3]
    out[1::2] = pcm24[2::3]
    return bytes(out)


class Session:
    """One device boot's worth of contiguous audio (the sample index restarts on reboot)."""

    def __init__(self, out: pathlib.Path, n: int, fs: int):
        suffix = "" if n == 1 else f"_s{n}"
        self.w24 = wave.open(str(out / f"audio_24bit{suffix}.wav"), "wb")
        self.w16 = wave.open(str(out / f"audio_16bit{suffix}.wav"), "wb")
        for w, width in ((self.w24, 3), (self.w16, 2)):
            w.setnchannels(1)
            w.setsampwidth(width)
            w.setframerate(fs)
        self.samples = 0
        self.next_idx = None
        self.gaps = []  # (at_sample, missing_samples)
        self.frames = 0

    def add(self, first_idx: int, n: int, data: bytes):
        if self.next_idx is not None and first_idx > self.next_idx:
            missing = first_idx - self.next_idx
            self.gaps.append((self.next_idx, missing))
            self._write(b"\x00" * (3 * missing))  # keep the timeline; gaps are reported, never hidden
        self._write(data)
        self.next_idx = first_idx + n
        self.frames += 1

    def _write(self, pcm24: bytes):
        self.w24.writeframes(pcm24)
        self.w16.writeframes(to_int16_bytes(pcm24))
        self.samples += len(pcm24) // 3

    def close(self):
        self.w24.close()
        self.w16.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--seconds", type=float, required=True, help="audio seconds to record")
    ap.add_argument("--label", required=True)
    ap.add_argument("--note", default="", help="free-text test conditions, stored in the summary")
    ap.add_argument("--reset", action="store_true", help="pulse RTS to reset the board and capture boot diagnostics")
    ap.add_argument("--fs", type=int, default=16000)
    ap.add_argument("--out-root", default=str(ROOT / "evidence" / "runs"))
    args = ap.parse_args()

    port, port_kind = (args.port, "user-specified") if args.port else find_port()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = pathlib.Path(args.out_root) / f"{stamp}_{args.label}"
    out.mkdir(parents=True, exist_ok=True)

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, args.baud, 0.05
    ser.dtr = False
    ser.rts = False
    ser.open()
    if args.reset:
        ser.rts = True
        time.sleep(0.2)
        ser.rts = False

    buf = bytearray()
    boot_raw = bytearray()
    sessions = [Session(out, 1, args.fs)]
    crc_errors = bad_len = 0
    events, last_stats = [], None
    log = open(out / "device_log.txt", "w", encoding="utf-8")
    t_start = time.time()
    t_first_audio = None
    last_print = 0.0
    target = int(args.seconds * args.fs)

    try:
        while True:
            chunk = ser.read(8192)
            if chunk:
                buf += chunk
            while True:
                i = buf.find(SYNC)
                if i < 0:
                    keep = len(SYNC) - 1
                    if len(buf) > keep:
                        boot_raw += buf[:-keep]
                        del buf[:-keep]
                    break
                if i:
                    boot_raw += buf[:i]
                    del buf[:i]
                if len(buf) < HDR:
                    break
                ftype, length = buf[4], struct.unpack_from("<H", buf, 6)[0]
                if length > MAX_PAYLOAD:
                    bad_len += 1
                    del buf[:1]
                    continue
                if len(buf) < HDR + length + CRC_LEN:
                    break
                body = bytes(buf[4:HDR + length])
                crc = struct.unpack_from("<H", buf, HDR + length)[0]
                if crc16_ccitt(body) != crc:
                    crc_errors += 1
                    del buf[:1]
                    continue
                payload = body[4:]
                del buf[:HDR + length + CRC_LEN]

                if ftype == T_AUDIO:
                    first_idx, bps, _slot, n = struct.unpack_from("<IBBH", payload, 0)
                    if bps != 3 or len(payload) != 8 + 3 * n:
                        bad_len += 1
                        continue
                    s = sessions[-1]
                    if s.next_idx is not None and first_idx < s.next_idx:
                        sessions.append(Session(out, len(sessions) + 1, args.fs))  # device rebooted
                        s = sessions[-1]
                        print("\n  !! device restarted its sample counter (reboot?) — new session file")
                    if t_first_audio is None:
                        t_first_audio = time.time()
                    s.add(first_idx, n, payload[8:])
                elif ftype == T_TEXT:
                    text = payload.decode("utf-8", "replace")
                    log.write(f"{time.time() - t_start:9.3f} {text}" + ("" if text.endswith("\n") else "\n"))
                    if text.startswith("@"):
                        rec = parse_kv(text)
                        rec["host_t"] = round(time.time() - t_start, 3)
                        events.append(rec)
                        if rec["type"] == "STATS":
                            last_stats = rec
                        else:
                            print("\n" + text.strip(), end="")

            now = time.time()
            if last_stats and now - last_print >= 1.0:
                last_print = now
                got = sum(s.samples for s in sessions)
                print(f"\r  recorded {got / args.fs:8.1f}/{args.seconds:.0f} s   level {last_stats.get('level_dbfs')} dBFS"
                      f"   i2s_ovf={last_stats.get('i2s_ovf')} pool_drops={last_stats.get('pool_drops')}"
                      f" link_drops={last_stats.get('link_drops')} crc_err={crc_errors}   ", end="", flush=True)
            if sum(s.samples for s in sessions) >= target:
                break
            if t_first_audio is None and now - t_start > 20:
                print("\nNo audio frames within 20 s. Is the M1 firmware flashed and the port correct?")
                break
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        ser.close()
        log.close()
        for s in sessions:
            s.close()
    print()

    (out / "boot_raw.txt").write_text(boot_raw.decode("latin-1"), encoding="utf-8")
    with open(out / "device_events.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    summary = {
        "label": args.label,
        "note": args.note,
        "host_start_local": dt.datetime.fromtimestamp(t_start).isoformat(timespec="seconds"),
        "port": port,
        "port_kind": port_kind,
        "baud": args.baud,
        "reset_by_host": args.reset,
        "fs_hz": args.fs,
        "sessions": [{"samples": s.samples, "seconds": round(s.samples / args.fs, 3), "audio_frames": s.frames,
                      "host_gap_count": len(s.gaps), "host_gap_samples": sum(g[1] for g in s.gaps),
                      "host_gaps_first50": s.gaps[:50]} for s in sessions],
        "crc_errors": crc_errors,
        "bad_length_frames": bad_len,
        "device_last_stats": last_stats,
        "device_boot": next((e for e in events if e["type"] == "BOOT"), None),
        "device_cfg": next((e for e in events if e["type"] == "CFG"), None),
        "int16_derivation": "int16 = int24 >> 8 (arithmetic) == I2S 32-bit word >> 16",
    }
    (out / "capture_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    s0 = summary["sessions"][0]
    ls = last_stats or {}
    print(f"Saved run: {out}")
    print(f"  {s0['seconds']} s audio | sessions {len(sessions)} | host gaps {s0['host_gap_count']} | crc errors {crc_errors}"
          f" | device i2s_ovf {ls.get('i2s_ovf')} pool_drops {ls.get('pool_drops')} link_drops {ls.get('link_drops')}")


if __name__ == "__main__":
    main()
