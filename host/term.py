"""Run a command in THIS classic console window (start it with `conhost.exe python host/term.py ...`) after setting the
window title, a Consolas font size, ANSI colour support and an exact on-screen rectangle (the visible frame, not the
invisible resize border). Used to lay out the real program windows for the demo recording.

Usage: conhost.exe python host/term.py --title T --rect x,y,w,h --font 18 -- <command ...>
"""
import argparse
import ctypes
import subprocess
import sys
from ctypes import wintypes

k32, u32, dwm = ctypes.windll.kernel32, ctypes.windll.user32, ctypes.windll.dwmapi


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class FONTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("nFont", ctypes.c_ulong), ("dwFontSize", COORD),
                ("FontFamily", ctypes.c_uint), ("FontWeight", ctypes.c_uint), ("FaceName", ctypes.c_wchar * 32)]


def place(x, y, w, h):
    hw = k32.GetConsoleWindow()
    u32.SetWindowPos(hw, 0, x, y, w, h, 0x0040)  # SWP_SHOWWINDOW
    outer, vis = wintypes.RECT(), wintypes.RECT()
    u32.GetWindowRect(hw, ctypes.byref(outer))
    dwm.DwmGetWindowAttribute(hw, 9, ctypes.byref(vis), ctypes.sizeof(vis))  # DWMWA_EXTENDED_FRAME_BOUNDS
    l, t = vis.left - outer.left, vis.top - outer.top
    r, b = outer.right - vis.right, outer.bottom - vis.bottom
    u32.SetWindowPos(hw, 0, x - l, y - t, w + l + r, h + t + b, 0x0040)


def main():
    argv = sys.argv[1:]
    cut = argv.index("--")
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="")
    ap.add_argument("--rect", required=True)
    ap.add_argument("--font", type=int, default=18)
    args = ap.parse_args(argv[:cut])
    cmd = argv[cut + 1:]
    out = k32.GetStdHandle(-11)
    f = FONTINFO()
    f.cbSize = ctypes.sizeof(FONTINFO)
    f.dwFontSize = COORD(0, args.font)
    f.FontFamily, f.FontWeight, f.FaceName = 54, 400, "Consolas"
    k32.SetCurrentConsoleFontEx(out, False, ctypes.byref(f))
    mode = wintypes.DWORD()
    k32.GetConsoleMode(out, ctypes.byref(mode))
    k32.SetConsoleMode(out, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    if args.title:
        k32.SetConsoleTitleW(args.title)
    place(*[int(v) for v in args.rect.split(",")])
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
