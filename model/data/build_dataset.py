"""Build windowed train/val sets exactly as the device sees them.

Every example is a WIN-frame (1.0 s) int8 feature window produced by the host twin running over a
continuous int16 stream: [2.5 s device-recorded room bed] + [clip mixed into the continuing bed].
The twin starts from reset at the stream start, so noise-reduction/PCAN state is settled by the
time the clip arrives (as on the always-on device).

Labels (end-of-keyword labelling, architecture §8.6 / X13):
  positive  window ends 0..160 ms after the keyword's acoustic end
  negative  window ends >=150 ms before the keyword end (prefix "Hey Vy..."), or any non-keyword audio
  masked    in between — not used
Real speaker S01 is excluded entirely (held-out test speaker).

Usage (WSL venv): python model/data/build_dataset.py --out ~/ps26172_data/ds_v0
"""
import argparse
import csv
import hashlib
import json
import pathlib
import sys
import time
import wave
from math import gcd

import numpy as np
import soundfile as sf
from scipy import signal

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.frontend.psfe import Frontend  # noqa: E402

FS, HOP, FE_WIN, WIN = 16000, 160, 480, 100
WARM = int(2.5 * FS)
SOS = signal.butter(4, [125, 6500], btype="band", fs=FS, output="sos")
SRC_CODES = {"tts_pos": 0, "tts_prefix": 1, "tts_neg": 2, "libri": 3, "ambient": 4}


def read_wav16(path):
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2 and w.getframerate() == FS
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def band_rms(x):
    return float(np.sqrt(np.mean(signal.sosfilt(SOS, x.astype(np.float64)) ** 2)) + 1e-9)


def to16k(x, sr):
    if sr == FS:
        return x.astype(np.float64)
    g = gcd(FS, sr)
    return signal.resample_poly(x.astype(np.float64), FS // g, sr // g)


def trim(x, rel_db=-35.0):
    """Trim leading/trailing silence of a clean clip (10 ms energy frames)."""
    n = len(x) // HOP
    e = np.sqrt(np.mean(x[: n * HOP].reshape(n, HOP) ** 2, axis=1)) + 1e-12
    on = np.where(e > e.max() * 10 ** (rel_db / 20))[0]
    return x[on[0] * HOP:(on[-1] + 1) * HOP] if len(on) else x


def end_frame(sample_end):
    """First feature frame whose window has consumed sample_end samples."""
    return int(np.ceil((sample_end - FE_WIN) / HOP))


class Beds:
    def __init__(self, files, skip_s, rng):
        self.rng = rng
        self.parts = [read_wav16(f)[int(skip_s * FS):] for f in files]
        self.parts = [p for p in self.parts if len(p) > FS]
        self.seconds = sum(len(p) for p in self.parts) / FS

    def sample(self, n):
        out = np.empty(0, dtype=np.float64)
        while len(out) < n:
            p = self.parts[self.rng.integers(len(self.parts))]
            take = min(n - len(out), len(p))
            o = self.rng.integers(0, len(p) - take + 1)
            out = np.concatenate([out, p[o:o + take].astype(np.float64)])
        return out * 10 ** (self.rng.uniform(-10, 4) / 20)  # quieter / louder rooms than the one recorded


class Builder:
    def __init__(self, fe, beds, rng):
        self.fe, self.beds, self.rng = fe, beds, rng
        self.x, self.y, self.src = [], [], []

    def stream(self, clip, snr_db, tail_s=0.4):
        bed = self.beds.sample(WARM + len(clip) + int(tail_s * FS))
        g = band_rms(bed) / band_rms(clip) * 10 ** (snr_db / 20)
        s = bed.copy()
        s[WARM:WARM + len(clip)] += clip * g
        feats = self.fe.to_int8(self.fe.features(np.clip(np.round(s), -32768, 32767).astype(np.int16)))
        return feats, end_frame(WARM + len(clip))

    def add(self, feats, ends, label, src):
        for e in ends:
            if WIN - 1 <= e < len(feats):
                self.x.append(feats[e - WIN + 1:e + 1])
                self.y.append(label)
                self.src.append(SRC_CODES[src])


def build_split(split, cfg, fe, rng, args):
    beds = Beds([pathlib.Path(cfg["runs_root"]) / f for f in cfg[f"bed_{split}"]], cfg["bed_skip_start_s"], rng)
    b = Builder(fe, beds, rng)
    t0 = time.time()
    tts_root = pathlib.Path(cfg["tts_root"])
    rows = [r for r in csv.DictReader(open(tts_root / "manifest.csv", encoding="utf-8")) if r["split"] == split]
    for r in rows:
        clip, sr = sf.read(tts_root / r["file"], dtype="float64")
        clip = trim(to16k(clip, sr))
        reps = args.pos_reps if r["label"] == "pos" else 1
        for _ in range(reps):
            feats, fe_end = b.stream(clip, rng.uniform(0, 25))
            if r["label"] == "pos":
                b.add(feats, fe_end + rng.choice(17, 3, replace=False), 1, "tts_pos")
                b.add(feats, [fe_end - 20, fe_end - 35], 0, "tts_prefix")
            else:
                b.add(feats, [fe_end, fe_end + 8, fe_end + 16, fe_end - 20], 0, "tts_neg")
    print(f"[{split}] tts: {len(rows)} clips -> {len(b.y)} windows, {time.time() - t0:.0f} s", flush=True)

    spk = sorted(p.name for p in pathlib.Path(cfg["librispeech_root"]).iterdir())
    nv = cfg["librispeech_val_speakers"]
    spk = spk[-nv:] if split == "val" else spk[:-nv]
    flacs = [f for s in spk for f in sorted((pathlib.Path(cfg["librispeech_root"]) / s).rglob("*.flac"))]
    n0 = len(b.y)
    for f in flacs[:: args.libri_stride]:
        a, _ = sf.read(f, dtype="float64")
        a = a[: int(5 * FS)] * 32768
        feats, fe_end = b.stream(a, rng.uniform(5, 30))
        b.add(feats, range(end_frame(WARM) + 10, fe_end + 30, 8), 0, "libri")
    print(f"[{split}] librispeech: {len(flacs[::args.libri_stride])} utt -> {len(b.y) - n0} windows", flush=True)

    n0 = len(b.y)
    for _ in range(args.ambient_streams if split == "train" else args.ambient_streams // 4):
        feats, fe_end = b.stream(np.zeros(int(8 * FS)), 0.0)
        b.add(feats, range(end_frame(WARM), len(feats), 10), 0, "ambient")
    print(f"[{split}] ambient: {len(b.y) - n0} windows (bed {beds.seconds:.0f} s)", flush=True)
    return np.stack(b.x).astype(np.int8), np.array(b.y, np.uint8), np.array(b.src, np.uint8), beds.seconds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=26172)
    ap.add_argument("--pos-reps", type=int, default=2)
    ap.add_argument("--libri-stride", type=int, default=1)
    ap.add_argument("--ambient-streams", type=int, default=400)
    args = ap.parse_args()
    cfg = json.loads((ROOT / "model" / "data" / "sources.json").read_text(encoding="utf-8"))
    out = pathlib.Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    fe = Frontend()
    meta = {"frontend_sha256": fe.sha256, "seed": args.seed, "args": vars(args), "win_frames": WIN,
            "sources_json_sha256": hashlib.sha256((ROOT / "model/data/sources.json").read_bytes()).hexdigest(),
            "src_codes": SRC_CODES, "splits": {}}
    for i, split in enumerate(("train", "val")):
        x, y, src, bed_s = build_split(split, cfg, fe, np.random.default_rng(args.seed + i), args)
        np.savez_compressed(out / f"{split}.npz", x=x, y=y, src=src)
        meta["splits"][split] = {"windows": int(len(y)), "positives": int(y.sum()), "bed_seconds": round(bed_s, 1),
                                 "by_source": {k: int((src == v).sum()) for k, v in SRC_CODES.items()}}
        print(split, meta["splits"][split], flush=True)
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
