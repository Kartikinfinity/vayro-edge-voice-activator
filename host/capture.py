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
T_AUDIO, T_TEXT, T_FEATURES, T_POSTERIOR = 1, 2, 3, 4
HDR, CRC_LEN, MAX_PAYLOAD = 8, 2, 1024
ESP_VIDS = {0x303A: "Espressif native USB-Serial-JTAG", 0x10C4: "Silicon Labs CP210x",
            0x1A86: "WCH CH34x", 0x0403: "FTDI"}
ROOT = pathlib.Path(__file__).resolve().parents[1]


def crc16_ccitt(data: bytes) -> int:
    # CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection) — same as the firmware.
    return binascii.crc_hqx(data, 0xFFFF)


def esp_ports():
    return [p for p in list_ports.comports() if p.vid in ESP_VIDS]


def find_port():
    hits = esp_ports()
    if len(hits) != 1:
        found = ", ".join(f"{p.device} ({p.description}, VID={p.vid})" for p in list_ports.comports())
        sys.exit(f"Expected exactly one ESP32 serial port, found: {found or 'none'}. Use --port.")
    return hits[0].device, ESP_VIDS[hits[0].vid]


def port_present(port):
    return any(p.device == port for p in list_ports.comports())


def open_port(port, baud, timeout_s=10.0):
    """Open without asserting DTR/RTS (which would hold the chip in reset); retry while Windows
    finishes enumerating a freshly (re)connected USB device."""
    t0 = time.time()
    while True:
        try:
            ser = serial.Serial()
            ser.port, ser.baudrate, ser.timeout = port, baud, 0.05
            ser.dtr = False
            ser.rts = False
            ser.open()
            if hasattr(ser, "set_buffer_size"):
                ser.set_buffer_size(rx_size=1 << 20)  # Windows driver buffer: absorb host scheduling stalls
            return ser
        except serial.SerialException:
            if time.time() - t0 > timeout_s:
                raise
            time.sleep(0.2)


def pulse_reset(ser):
    """Hold EN low for 200 ms via RTS. Re-writing DTR after each RTS change is esptool's workaround
    for Windows usbser.sys, which otherwise does not forward the new line state to the device
    (a bare RTS pulse silently failed to reset the board in run 20260927_125042)."""
    ser.dtr = False
    ser.rts = True
    ser.dtr = ser.dtr
    time.sleep(0.2)
    ser.rts = False
    ser.dtr = ser.dtr


def reset_and_reopen(ser, port, baud):
    pulse_reset(ser)
    ser.close()
    time.sleep(0.5)  # native USB re-enumerates on reset
    wait_until(lambda: port_present(port), 10, "port did not come back after reset")
    return open_port(port, baud)


def wait_until(pred, timeout_s, msg):
    t0 = time.time()
    while not pred():
        if time.time() - t0 > timeout_s:
            sys.exit(f"Timed out: {msg}")
        time.sleep(0.1)


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
    """One device boot's worth of contiguous audio (the sample index restarts on reboot).
    With chunk_s > 0 the WAVs rotate every chunk_s seconds (_c000, _c001, ...), so a crash
    during a multi-hour recording loses at most the header of the open chunk."""

    def __init__(self, out: pathlib.Path, n: int, fs: int, chunk_s: float = 0):
        self.out, self.fs = out, fs
        self.suffix = "" if n == 1 else f"_s{n}"
        self.chunk = int(chunk_s * fs) if chunk_s else 0
        self.k = 0
        self.in_chunk = 0
        self.files = []
        self._open()
        self.samples = 0
        self.next_idx = None
        self.gaps = []  # (at_sample, missing_samples)
        self.frames = 0

    def _open(self):
        c = f"_c{self.k:03d}" if self.chunk else ""
        self.w24 = wave.open(str(self.out / f"audio_24bit{self.suffix}{c}.wav"), "wb")
        self.w16 = wave.open(str(self.out / f"audio_16bit{self.suffix}{c}.wav"), "wb")
        for w, width in ((self.w24, 3), (self.w16, 2)):
            w.setnchannels(1)
            w.setsampwidth(width)
            w.setframerate(self.fs)
        self.files.append(f"audio_24bit{self.suffix}{c}.wav")

    def add(self, first_idx: int, n: int, data: bytes):
        if self.next_idx is not None and first_idx > self.next_idx:
            missing = first_idx - self.next_idx
            self.gaps.append((self.next_idx, missing))
            self._write(b"\x00" * (3 * missing))  # keep the timeline; gaps are reported, never hidden
        self._write(data)
        self.next_idx = first_idx + n
        self.frames += 1

    def _write(self, pcm24: bytes):
        while pcm24:
            if self.chunk and self.in_chunk >= self.chunk:
                self.close()
                self.k += 1
                self.in_chunk = 0
                self._open()
            n = len(pcm24) // 3
            if self.chunk:
                n = min(n, self.chunk - self.in_chunk)
            part, pcm24 = pcm24[:3 * n], pcm24[3 * n:]
            self.w24.writeframes(part)
            self.w16.writeframes(to_int16_bytes(part))
            self.samples += n
            self.in_chunk += n

    def close(self):
        self.w24.close()
        self.w16.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--seconds", type=float, help="audio seconds to record (implied by --script)")
    ap.add_argument("--script", default="",
                    help='timed prompts "name:seconds,..." e.g. "silence:5,count 1 to 10 at 50 cm:7"; '
                         "boundaries are recorded in capture_summary.json")
    ap.add_argument("--script-file", default="", help='prompt file, one "label | seconds | prompt" per line')
    ap.add_argument("--settle-s", type=float, default=3.0,
                    help="with --script: seconds of audio recorded before the first prompt (mic settling)")
    ap.add_argument("--label", required=True)
    ap.add_argument("--note", default="", help="free-text test conditions, stored in the summary")
    ap.add_argument("--cold", action="store_true", help="guide an unplug/replug power cycle (cold boot) before capturing")
    ap.add_argument("--attach", action="store_true",
                    help="attach to an already-running board WITHOUT resetting it (default: warm reset, so every run "
                         "starts from a fresh boot; attaching after an earlier run stalled the USB link, run 20260926_221804)")
    ap.add_argument("--chunk-s", type=float, default=0, help="rotate WAV files every N seconds (long recordings)")
    ap.add_argument("--keep-awake", action="store_true",
                    help="Windows: hold ES_SYSTEM_REQUIRED while recording (released on exit; no settings changed)")
    ap.add_argument("--wall-s", type=float, default=0,
                    help="stop after this many WALL seconds regardless of audio (product builds stream no audio)")
    ap.add_argument("--echo-stats", action="store_true", help="also echo @STATS/@PERF lines to stdout (live dashboards)")
    ap.add_argument("--color", action="store_true", help="ANSI colour for @KW/@STREAM/@CPU/@MEM lines (demo console)")
    ap.add_argument("--send", default="", help='timed host->device bytes, e.g. "T@20,T@35" (T = synthetic trigger)')
    ap.add_argument("--fs", type=int, default=16000)
    ap.add_argument("--out-root", default=str(ROOT / "evidence" / "runs"))
    args = ap.parse_args()

    script = []  # (label, seconds, prompt)
    for item in filter(None, (s.strip() for s in args.script.split(","))):
        name, _, dur = item.rpartition(":")
        script.append((name.strip(), float(dur), name.strip()))
    if args.script_file:
        for line in pathlib.Path(args.script_file).read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                label, dur, prompt = (p.strip() for p in line.split("|", 2))
                script.append((label, float(dur), prompt))
    starts, t = [], args.settle_s
    for _, dur, _ in script:
        starts.append(t)
        t += dur
    if script:
        args.seconds = t + 0.5
    if args.wall_s and not args.seconds:
        args.seconds = 1e9  # text-only run: bounded by --wall-s
    if not args.seconds:
        sys.exit("Give --seconds, --wall-s or --script")
    sends = sorted((float(at), ch.encode()) for ch, _, at in (s.strip().partition("@") for s in args.send.split(",") if s.strip()))

    if sys.platform == "win32":
        import ctypes
        # HIGH_PRIORITY_CLASS: host CPU load (training/eval) once stalled the reader for >0.3 s and lost 0.23 s of
        # audio (run 20260927_134535, gap at 2293.9 s). The reader is light, so priority costs nothing.
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00000080)
        if args.keep_awake:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

    port, port_kind = (args.port, "user-specified") if args.port else find_port()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = pathlib.Path(args.out_root) / f"{stamp}_{args.label}"
    out.mkdir(parents=True, exist_ok=True)

    boot_kind = "already running"
    if args.cold:
        print(f">>> UNPLUG the ESP32-S3 USB cable now ({port}) ...")
        wait_until(lambda: not port_present(port), 120, "board was not unplugged")
        print(">>> Unplugged. Wait ~2 s, then PLUG it back in ...")
        time.sleep(1.0)
        wait_until(lambda: port_present(port), 120, "board did not reappear")
        boot_kind = "cold (USB power cycle observed by host)"
        ser = open_port(port, args.baud)
    else:
        ser = open_port(port, args.baud)
        if not args.attach:
            ser = reset_and_reopen(ser, port, args.baud)
            boot_kind = "warm (RTS reset)"
    print(f"Port {port} open ({port_kind}); boot: {boot_kind}")

    buf = bytearray()
    boot_raw = bytearray()
    sessions = [Session(out, 1, args.fs, args.chunk_s)]
    crc_errors = bad_len = 0
    events, last_stats, last_perf = [], None, None
    log = open(out / "device_log.txt", "w", encoding="utf-8")
    t_start = time.time()
    t_first_audio = None
    last_print = 0.0
    target = int(args.seconds * args.fs)

    got_frame = False
    last_kick = 0.0
    port_losses = 0
    prompt_i, script_done, previewed = -1, False, {}
    # A fresh boot sends @BOOT before any audio; audio first means the reset did not happen.
    expect_boot, seen_boot, reset_retries, auto_resets = not args.attach, False, 0, 0
    recv_samples, wd_t, wd_recv = 0, time.time(), 0  # stall watchdog: real (non-gap) samples received
    streaming = False  # watchdog windows start at the first audio frame of each boot (boot probes take ~3 s)
    side_files, side_session, feat_frames, post_frames = {}, {}, 0, 0
    try:
        while True:
            if not got_frame and time.time() - last_kick > 0.25:
                ser.write(b"S")  # firmware holds the mic clock off until it hears from the host
                last_kick = time.time()
            try:
                chunk = ser.read(8192)
            except serial.SerialException:
                port_losses += 1
                print("\n  !! serial port lost (device reset or unplugged) — reopening")
                ser.close()
                wait_until(lambda: port_present(port), 30, "port did not come back")
                ser = open_port(port, args.baud)
                got_frame = False
                continue
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
                got_frame = True

                if ftype == T_AUDIO:
                    first_idx, bps, _slot, n = struct.unpack_from("<IBBH", payload, 0)
                    if bps != 3 or len(payload) != 8 + 3 * n:
                        bad_len += 1
                        continue
                    if expect_boot and not seen_boot:
                        if reset_retries >= 2:
                            sys.exit("\nBoard keeps streaming from an old boot and will not reset. "
                                     "Unplug and replug the USB cable, then run again.")
                        reset_retries += 1
                        print(f"\n  !! audio arrived before @BOOT (board did not reset) — reset retry {reset_retries}")
                        ser = reset_and_reopen(ser, port, args.baud)
                        buf.clear()
                        got_frame = False
                        break
                    if not streaming:
                        streaming, wd_t, wd_recv = True, time.time(), recv_samples
                    recv_samples += n
                    s = sessions[-1]
                    if s.next_idx is not None and first_idx < s.next_idx:
                        sessions.append(Session(out, len(sessions) + 1, args.fs, args.chunk_s))  # device rebooted
                        s = sessions[-1]
                        print("\n  !! device restarted its sample counter (reboot?) — new session file")
                    if t_first_audio is None:
                        t_first_audio = time.time()
                    s.add(first_idx, n, payload[8:])
                elif ftype in (T_FEATURES, T_POSTERIOR):
                    # Device front-end output (u32 frame_idx, u32 end_sample, u16 bands, bands x u16) and model
                    # output (u32 frame, i8 raw, u8 trigger). Stored per boot session to align with its audio file.
                    if not seen_boot and expect_boot:
                        continue
                    kind = "features" if ftype == T_FEATURES else "posteriors"
                    if side_session.get(kind) != len(sessions):
                        if side_files.get(kind):
                            side_files[kind].close()
                        side_session[kind] = len(sessions)
                        sfx = "" if len(sessions) == 1 else f"_s{len(sessions)}"
                        side_files[kind] = open(out / f"{kind}_device{sfx}.bin", "wb")
                    side_files[kind].write(payload)
                    if ftype == T_FEATURES:
                        feat_frames += 1
                    else:
                        post_frames += 1
                elif ftype == T_TEXT:
                    text = payload.decode("utf-8", "replace")
                    log.write(f"{time.time() - t_start:9.3f} {text}" + ("" if text.endswith("\n") else "\n"))
                    if text.startswith("@"):
                        rec = parse_kv(text)
                        rec["host_t"] = round(time.time() - t_start, 3)
                        events.append(rec)
                        if rec["type"] == "BOOT":
                            seen_boot = True
                        if rec["type"] == "STATS":
                            last_stats = rec
                        elif rec["type"] == "PERF":
                            last_perf = rec
                        if rec["type"] not in ("STATS", "PERF") or args.echo_stats:
                            line = text.strip()
                            if args.color:  # demo console: highlight the lines a viewer should notice
                                col = {"KW": "92", "STREAM": "96", "CPU": "93", "MEM": "93"}.get(rec["type"])
                                line = f"\x1b[{col}m{line}\x1b[0m" if col else line
                            print("\n" + line, end="")
                    log.flush()

            now = time.time()
            while sends and got_frame and now - t_start >= sends[0][0]:
                at, ch = sends.pop(0)
                ser.write(ch)
                print(f"\n  -> sent {ch.decode()!r} at host t={now - t_start:.1f} s", flush=True)
            if args.wall_s and now - t_start >= args.wall_s:
                break
            # Stall watchdog: <80 % of real-time audio over 10 s (after the first audio) -> reset the board
            # into a new session. Such gaps stay in the WAV timeline and in the summary.
            if streaming and now - wd_t >= 10.0:
                if (recv_samples - wd_recv) < 0.8 * (now - wd_t) * args.fs:
                    auto_resets += 1
                    print(f"\n  !! link stall: {(recv_samples - wd_recv) / args.fs:.1f} s of audio in {now - wd_t:.0f} s "
                          f"— auto-reset #{auto_resets}")
                    ser = reset_and_reopen(ser, port, args.baud)
                    buf.clear()
                    got_frame, seen_boot, expect_boot, streaming = False, False, True, False
                wd_t, wd_recv = now, recv_samples
            rec_s = sessions[0].samples / args.fs
            if script and t_first_audio is not None:
                if prompt_i == -1:
                    print(f"\n\n>>> Stay QUIET — mic settling ({args.settle_s:.0f} s)", flush=True)
                    prompt_i = 0
                # "next:" preview 1.2 s before each prompt, so the speaker is ready and speaks early in the window
                # (session kw_S01_s2 showed utterances drifting to the window end / into the next prompt).
                if prompt_i < len(script) and not previewed.get(prompt_i) and rec_s >= starts[prompt_i] - 1.2:
                    print(f"\n    next: {script[prompt_i][2]}", flush=True)
                    previewed[prompt_i] = True
                while prompt_i < len(script) and rec_s >= starts[prompt_i]:
                    _, dur, prompt = script[prompt_i]
                    print(f">>> [{prompt_i + 1}/{len(script)}] ({dur:g} s)   {prompt.upper()}   <-- NOW", flush=True)
                    prompt_i += 1
                if prompt_i == len(script) and rec_s >= starts[-1] + script[-1][1] and not script_done:
                    print("\n>>> DONE — you can stop.", flush=True)
                    script_done = True
            elif last_stats and now - last_print >= 1.0:
                last_print = now
                got = sum(s.samples for s in sessions)
                print(f"\r  recorded {got / args.fs:8.1f}/{args.seconds:.0f} s   level {last_stats.get('level_dbfs')} dBFS"
                      f"   i2s_ovf={last_stats.get('i2s_ovf')} pool_drops={last_stats.get('pool_drops')}"
                      f" link_drops={last_stats.get('link_drops')} crc_err={crc_errors}   ", end="", flush=True)
            if sum(s.samples for s in sessions) >= target:
                break
            if t_first_audio is None and not args.wall_s and now - t_start > 20:
                print("\nNo audio frames within 20 s. Is the M1 firmware flashed and the port correct?")
                break
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        ser.close()
        log.close()
        for s in sessions:
            s.close()
        for fh in side_files.values():
            fh.close()
    print()

    (out / "boot_raw.txt").write_text(boot_raw.decode("latin-1"), encoding="utf-8")
    with open(out / "device_events.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    summary = {
        "label": args.label,
        "note": args.note,
        "host_start_local": dt.datetime.fromtimestamp(t_start).isoformat(timespec="seconds"),
        "host_t0_epoch": round(t_start, 3),  # host_t of every event is relative to this wall time
        "port": port,
        "port_kind": port_kind,
        "baud": args.baud,
        "boot": boot_kind,
        "port_losses": port_losses,
        "reset_retries": reset_retries,
        "auto_resets_on_stall": auto_resets,
        "fs_hz": args.fs,
        "sessions": [{"files": s.files, "samples": s.samples, "seconds": round(s.samples / args.fs, 3), "audio_frames": s.frames,
                      "host_gap_count": len(s.gaps), "host_gap_samples": sum(g[1] for g in s.gaps),
                      "host_gaps_first50": s.gaps[:50]} for s in sessions],
        "settle_s": args.settle_s if script else None,
        "script_file": args.script_file or None,
        "script_segments": [{"name": n, "prompt": p, "t0_s": round(s0, 3), "t1_s": round(s0 + d, 3)}
                            for (n, d, p), s0 in zip(script, starts)],
        "script_timing_note": "boundaries are when the prompt was printed (audio-sample clock, ~50 ms resolution); "
                              "speaker reaction lag is not compensated — analysis trims segment starts",
        "device_feature_frames": feat_frames,
        "device_posterior_frames": post_frames,
        "device_kw_triggers": [e for e in events if e["type"] == "KW"],
        "crc_errors": crc_errors,
        "bad_length_frames": bad_len,
        "device_last_stats": last_stats,
        "device_last_perf": last_perf,
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
