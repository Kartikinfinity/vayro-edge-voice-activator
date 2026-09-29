"""Plain prompt window for the demo recording (runs inside host/term.py). Tells the speaker what to say and when.

  --mode demo        waits for <take>/start_epoch.txt (written when the board is connected), then runs the schedule
  --mode efficiency  shows one static line
Before anything else it can show a 0.4 s white screen (sync marker for audio/video alignment) when
<take>/flash_request.txt appears, and logs the wall time of that flash to <take>/flash.json.
"""
import argparse
import json
import os
import pathlib
import time

SCHEDULE = [("Say:  Hey Vayro ... turn on the light", 13), ("Say:  Hey Vayro ... what time is it", 13),
            ("Say:  Hey Vayro ... play some music", 13), ("Say:  Hey Vayro ... open the door", 13),
            ("Now talk normally, WITHOUT the keyword", 12)]
ESC = "\x1b["


def show(lines, color="97"):
    os.system("")  # keep VT mode on
    print(f"{ESC}0m{ESC}2J{ESC}H", end="")
    for text, c in lines:
        print(f"{ESC}{c or color}m {text}{ESC}0m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--take", required=True)
    ap.add_argument("--mode", choices=["demo", "efficiency"], default="demo")
    args = ap.parse_args()
    take = pathlib.Path(args.take)
    show([("", None), ("Waiting for the board ...", "90")])
    while not (take / "flash_request.txt").exists():
        time.sleep(0.05)
    print(f"{ESC}47m{ESC}2J", end="", flush=True)  # white screen = sync marker
    t_flash = time.time()
    time.sleep(0.4)
    (take / "flash.json").write_text(json.dumps({"flash_wall": t_flash}), encoding="utf-8")
    if args.mode == "efficiency":
        show([("", None), ("Product firmware - idle listening", "97"), ("nothing is streamed; watch core1_busy", "90"),
              ("in the @CPU lines (every 10 s)", "90")])
        while not (take / "stop.txt").exists():
            time.sleep(0.2)
        return
    show([("", None), ("Waiting for the board to connect ...", "90")])
    while not (take / "start_epoch.txt").exists():
        time.sleep(0.05)
    t0 = float((take / "start_epoch.txt").read_text())
    last = None
    while True:
        el = time.time() - t0
        if el < 0:
            state = ("", None), ("Get ready - stay quiet", "97"), (f"starting in {int(-el) + 1} s", "90")
        else:
            acc, cur = 0, None
            for k, (txt, dur) in enumerate(SCHEDULE):
                if el < acc + dur:
                    cur = (txt, acc + dur - el, k)
                    break
                acc += dur
            if cur is None:
                show([("", None), ("Done - thank you", "92")])
                return
            txt, left, k = cur
            nxt = SCHEDULE[k + 1][0] if k + 1 < len(SCHEDULE) else ""
            bar = "#" * int(left / SCHEDULE[k][1] * 30)
            state = (("", None), (txt, "93" if txt.startswith("Say") else "97"), (bar, "36"),
                     (f"next: {nxt}" if nxt else "", "90"))
        key = tuple(state)
        if key != last:
            show(list(state))
            last = key
        time.sleep(0.1)


if __name__ == "__main__":
    main()
