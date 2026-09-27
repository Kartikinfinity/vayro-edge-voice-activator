"""Gracefully stop a console process started hidden (e.g. a detached capture.py) by delivering a real
CTRL_C_EVENT to its console, so it finalises WAV headers and writes its summary. Windows only.
Usage: python tools/send_ctrl_c.py <pid>"""
import ctypes
import sys
import time

k = ctypes.windll.kernel32
pid = int(sys.argv[1])
k.FreeConsole()
if not k.AttachConsole(pid):
    sys.exit(f"AttachConsole({pid}) failed: {ctypes.GetLastError()}")
k.SetConsoleCtrlHandler(None, True)  # this helper ignores the event itself
k.GenerateConsoleCtrlEvent(0, 0)     # CTRL_C_EVENT to every process on the attached console
time.sleep(2)
k.FreeConsole()
