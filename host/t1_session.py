"""T1: keyword-end -> server latency on the exact final configuration (product firmware v2b + threaded ASR server).
Starts the ASR server and the device console hidden (both log to files), waits for the board to connect, then opens a
visible prompt window (host/prompter.py, script host/scripts/t1_latency.txt). Afterwards run
`server/latency_report.py <server session>`.
Usage (host venv): python host/t1_session.py
"""
import datetime as dt
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv-host" / "Scripts" / "python.exe")
ASR_MODEL = r"D:\ps26172_ext\vosk\vosk-model-en-in-0.5"


def listening(port=5005):
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    return re.search(rf"0\.0\.0\.0:{port}\s+0\.0\.0\.0:0\s+LISTENING", out) is not None


def main():
    take = ROOT / "evidence" / "t1" / f"{dt.datetime.now():%Y%m%d_%H%M%S}"
    take.mkdir(parents=True)
    if listening():
        sys.exit("port 5005 already in use")
    srv = subprocess.Popen([PY, "-u", "server/ingest.py", "--port", "5005", "--asr", ASR_MODEL, "--min-after-s", "0.8",
                            "--stream-s-max", "6", "--status-file", str(take / "status.txt")], cwd=ROOT,
                           stdout=open(take / "server.log", "w"), stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    t = time.time()
    while not listening():
        if time.time() - t > 180:
            sys.exit("server did not start")
        time.sleep(0.3)
    dev = subprocess.Popen([PY, "-u", "host/capture.py", "--port", "COM7", "--wall-s", "130", "--label", "t1_latency_product",
                            "--note", "T1: product firmware v2b + ASR server, keyword only with pauses"], cwd=ROOT,
                           stdout=open(take / "device.log", "w"), stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    t = time.time()
    while "connected" not in ((take / "status.txt").read_text() if (take / "status.txt").exists() else ""):
        if time.time() - t > 90:
            sys.exit("board did not connect")
        time.sleep(0.2)
    time.sleep(2)
    prm = subprocess.Popen(["conhost.exe", PY, str(ROOT / "host" / "term.py"), "--title", "T1 - what to say", "--rect",
                            "260,220,920,360", "--font", "30", "--", PY, str(ROOT / "host" / "prompter.py"),
                            str(ROOT / "host" / "scripts" / "t1_latency.txt"), "t1_latency", "--settle-s", "3"], cwd=ROOT)
    prm.wait()
    time.sleep(6)  # last stream + transcript
    dev.wait(120)
    time.sleep(3)
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(srv.pid)], capture_output=True)
    sess = re.search(r"writing to (\S+)", (take / "server.log").read_text(encoding="utf-8", errors="replace"))
    (take / "meta.txt").write_text(f"server_session={sess.group(1) if sess else None}\n", encoding="utf-8")
    print("T1 done:", take, "server session:", sess.group(1) if sess else None)


if __name__ == "__main__":
    main()
