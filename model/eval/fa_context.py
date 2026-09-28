"""Characterise false-activation contexts in a long recording (training-split hours only):
for each device trigger, the 1.2 s of audio before it: speech-band (300-4000 Hz) level above the hour's floor,
high-band (4-8 kHz) share, voiced-periodicity (autocorrelation peak 80-400 Hz pitch), and the posterior."""
import pathlib
import sys
import wave

import numpy as np
from scipy import signal

run = pathlib.Path(sys.argv[1])
hours = [int(h) for h in sys.argv[2].split(",")]
FS = 16000
d = np.fromfile(run / "posteriors_device.bin", dtype=np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")]))
t_all = (480 + 160 * d["frame"].astype(np.int64)) / FS
trig = t_all[d["trig"] == 1]
sos_sp = signal.butter(4, [300, 4000], btype="band", fs=FS, output="sos")
sos_hi = signal.butter(4, [4000, 7800], btype="band", fs=FS, output="sos")
for h in hours:
    with wave.open(str(run / f"audio_16bit_c{h:03d}.wav")) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    sp, hi = signal.sosfilt(sos_sp, x), signal.sosfilt(sos_hi, x)
    fr = 320
    n = len(sp) // fr
    lev = 20 * np.log10(np.sqrt(np.mean(sp[: n * fr].reshape(n, fr) ** 2, axis=1)) + 1e-9)
    floor = np.percentile(lev, 20)
    for tt in trig[(trig >= h * 3600) & (trig < (h + 1) * 3600)]:
        a, b = int((tt - h * 3600 - 1.2) * FS), int((tt - h * 3600) * FS)
        seg, seg_hi = sp[a:b], hi[a:b]
        e_sp = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)
        e_hi = 20 * np.log10(np.sqrt(np.mean(seg_hi ** 2)) + 1e-9)
        # voicing: max normalised autocorrelation in the 2.5-12.5 ms lag range over 40 ms frames
        vo = []
        for k in range(0, len(seg) - 640, 320):
            f = seg[k:k + 640] - seg[k:k + 640].mean()
            ac = np.correlate(f, f, "full")[639:]
            vo.append(ac[40:200].max() / (ac[0] + 1e-9))
        p = (int(d["raw"][np.argmin(np.abs(t_all - tt))]) + 128) / 256
        clock = f"{int(tt // 3600) + 20}:{int(tt % 3600 // 60) + 31:02d}"
        print(f"t={tt:8.1f}s  speech-band {e_sp - floor:5.1f} dB over floor | hi-band vs speech {e_hi - e_sp:6.1f} dB | "
              f"voicing max {max(vo):.2f} median {np.median(vo):.2f} | p {p:.2f}")
