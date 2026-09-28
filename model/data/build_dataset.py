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
SRC_CODES = {"tts_pos": 0, "tts_prefix": 1, "tts_neg": 2, "libri": 3, "ambient": 4, "real_pos": 5, "real_neg": 6, "hard_neg": 7, "night_neg": 8,
             "tts_pos_cont": 9, "house_hard": 10, "house_neg": 11}


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

    def stream_cont(self, clip, cont, gap, snr_db, cont_db, tail_s=0.4):
        """v4: keyword clip, `gap` samples, then a continuation utterance (a command spoken straight after the
        keyword, M6 E-49/E-51). The keyword's SNR rule is unchanged; the continuation sits `cont_db` relative to the
        keyword's band level. Returns the KEYWORD's end frame, so labels stay end-of-keyword."""
        bed = self.beds.sample(WARM + len(clip) + gap + len(cont) + int(tail_s * FS))
        g = band_rms(bed) / band_rms(clip) * 10 ** (snr_db / 20)
        s = bed.copy()
        s[WARM:WARM + len(clip)] += clip * g
        o = WARM + len(clip) + gap
        s[o:o + len(cont)] += cont * (band_rms(clip) / band_rms(cont)) * g * 10 ** (cont_db / 20)
        feats = self.fe.to_int8(self.fe.features(np.clip(np.round(s), -32768, 32767).astype(np.int16)))
        return feats, end_frame(WARM + len(clip))

    def add(self, feats, ends, label, src):
        for e in ends:
            if WIN - 1 <= e < len(feats):
                self.x.append(feats[e - WIN + 1:e + 1])
                self.y.append(label)
                self.src.append(SRC_CODES[src])


def add_real_run(b, run, rng, copies):
    """Real device recording (scripted session): the whole session is one continuous stream, as on the
    device. Positives = windows ending 0..160 ms after each located keyword end; negatives = every 4th
    window farther than [start-0.3 s, end+1.2 s] from any keyword (includes the spoken confusables).
    `copies` extra versions add room bed at a random level (noise augmentation)."""
    sys.path.insert(0, str(ROOT))
    from model.eval.eval_stream import keyword_ends, load_run_audio  # noqa: E402
    audio = load_run_audio(run).astype(np.float64)
    kws, _, _, _ = keyword_ends(run, audio.astype(np.int16))
    for c in range(copies + 1):
        s = audio if c == 0 else audio + b.beds.sample(len(audio)) * 10 ** (rng.uniform(-12, 3) / 20)
        feats = b.fe.to_int8(b.fe.features(np.clip(np.round(s), -32768, 32767).astype(np.int16)))
        ends = [end_frame(int(k["t_end"] * FS)) for k in kws]
        for e in ends:
            b.add(feats, e + rng.choice(17, 3, replace=False), 1, "real_pos")
        near = np.zeros(len(feats), bool)
        for k in kws:
            near[max(0, end_frame(int((k["t_start"] - 0.3) * FS))):end_frame(int((k["t_end"] + 1.2) * FS)) + 1] = True
        b.add(feats, [e for e in range(WIN - 1, len(feats), 4) if not near[e]], 0, "real_neg")
    return len(kws)


def add_long_run_negatives(b, spec, rng):
    """Device-recorded long ambient run (training hours only): (1) HARD negatives = windows where the
    deployed model's device posterior was >= posterior_min (the moments that fooled it, incl. its live false
    activations), each +/-3 frames, replicated `hard_reps` times; (2) general negatives every `stride` frames.
    Device frame f in hour chunk k maps to chunk-local frame f - 360000*k (1 h = 360 000 hops)."""
    run = pathlib.Path(spec["run_dir"])
    dev = np.fromfile(run / "posteriors_device.bin", dtype=np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")]))
    p = (dev["raw"].astype(np.float32) + 128) / 256
    hard_frames = dev["frame"][p >= spec["posterior_min"]].astype(np.int64)
    n_hard = n_gen = 0
    for k in spec["chunks"]:
        with wave.open(str(run / f"audio_16bit_c{k:03d}.wav")) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        feats = b.fe.to_int8(b.fe.features(audio))
        lo = WIN - 1 + 250  # skip the first 2.5 s: twin state restarts at the chunk boundary
        local = hard_frames - 360000 * k
        local = local[(local >= lo) & (local < len(feats))]
        ends = sorted({int(e + d) for e in local for d in (-3, 0, 3) if lo <= e + d < len(feats)})
        for _ in range(spec["hard_reps"]):
            b.add(feats, ends, 0, "hard_neg")
        n_hard += len(ends)
        gen = range(lo, len(feats), spec["stride"])
        b.add(feats, gen, 0, "night_neg")
        n_gen += len(gen)
    return n_hard, n_gen


def add_session_negatives(b, spec):
    """v4: active-household recording made of several capture sessions (one per device boot). Each session's WAV
    chunks are concatenated and replayed from boot, so device frame numbers in that session's posteriors file are
    feature-frame indices. Hard negatives = frames where the deployed model's live posterior >= posterior_min
    (+/-3 frames, x hard_reps); general negatives every `stride` frames; `exclude_s` ranges (the M6 test, where the
    keyword WAS spoken) and the first 2.5 s after boot are skipped. Only the listed chunks are read, so held-out
    chunks never enter."""
    run = pathlib.Path(spec["run_dir"])
    n_hard = n_gen = 0
    for sess in spec["sessions"]:
        audio = np.concatenate([read_wav16(run / w) for w in sess["wavs"]])
        feats = b.fe.to_int8(b.fe.features(audio))
        dev = np.fromfile(run / sess["posteriors"], dtype=np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")]))
        p = (dev["raw"].astype(np.float32) + 128) / 256
        lo = WIN - 1 + 250
        keep = np.ones(len(feats), bool)
        keep[:lo] = False
        for a, z in sess.get("exclude_s", []):
            keep[max(0, int(a * 100) - WIN):int(z * 100) + WIN] = False  # no window may overlap the excluded span
        hard = dev["frame"][p >= spec["posterior_min"]].astype(np.int64)
        ends = sorted({int(e + d) for e in hard for d in (-3, 0, 3) if 0 <= e + d < len(feats) and keep[e + d]})
        for _ in range(spec["hard_reps"]):
            b.add(feats, ends, 0, "house_hard")
        gen = [e for e in range(lo, len(feats), spec["stride"]) if keep[e]]
        b.add(feats, gen, 0, "house_neg")
        n_hard += len(ends)
        n_gen += len(gen)
    return n_hard, n_gen


def build_split(split, cfg, fe, rng, args):
    bed_files = cfg[f"bed_{split}"] + (cfg.get(args.extra_beds, []) if split == "train" and args.extra_beds else [])
    beds = Beds([pathlib.Path(cfg["runs_root"]) / f for f in bed_files], cfg["bed_skip_start_s"], rng)
    b = Builder(fe, beds, rng)
    t0 = time.time()
    tts_root = pathlib.Path(args.tts_root or cfg["tts_root"]).expanduser()
    rows = [r for r in csv.DictReader(open(tts_root / "manifest.csv", encoding="utf-8")) if r["split"] == split]
    spk = sorted(p.name for p in pathlib.Path(cfg["librispeech_root"]).iterdir())
    nv = cfg["librispeech_val_speakers"]
    spk = spk[-nv:] if split == "val" else spk[:-nv]
    flacs = [f for s in spk for f in sorted((pathlib.Path(cfg["librispeech_root"]) / s).rglob("*.flac"))]

    def continuation():
        """0.5-1.5 s of this split's LibriSpeech speech (v4 keyword+command positives)."""
        a, _ = sf.read(flacs[rng.integers(len(flacs))], dtype="float64")
        n = int(rng.uniform(0.5, 1.5) * FS)
        o = int(rng.integers(0, max(1, len(a) - n)))
        return trim(a[o:o + n]) * 32768

    n_cont = 0
    for r in rows:
        clip, sr = sf.read(tts_root / r["file"], dtype="float64")
        clip = trim(to16k(clip, sr))
        reps = args.pos_reps if r["label"] == "pos" else 1
        for _ in range(reps):
            # no RNG draw when the option is off, so earlier datasets (v2, v3) rebuild identically
            cont_pos = r["label"] == "pos" and args.continuation > 0 and rng.random() < args.continuation
            if cont_pos:
                feats, fe_end = b.stream_cont(clip, continuation(), int(rng.uniform(0, 0.25) * FS),
                                              rng.uniform(0, 25), rng.uniform(-6, 3))
                n_cont += 1
            else:
                feats, fe_end = b.stream(clip, rng.uniform(0, 25))
            if r["label"] == "pos":
                b.add(feats, fe_end + rng.choice(17, 3, replace=False), 1, "tts_pos_cont" if cont_pos else "tts_pos")
                b.add(feats, [fe_end - 20, fe_end - 35], 0, "tts_prefix")
            else:
                b.add(feats, [fe_end, fe_end + 8, fe_end + 16, fe_end - 20], 0, "tts_neg")
    print(f"[{split}] tts: {len(rows)} clips -> {len(b.y)} windows ({n_cont} positive streams with a continuation), "
          f"{time.time() - t0:.0f} s", flush=True)

    n0 = len(b.y)
    for f in flacs[:: args.libri_stride]:
        a, _ = sf.read(f, dtype="float64")
        a = a[: int(5 * FS)] * 32768
        feats, fe_end = b.stream(a, rng.uniform(5, 30))
        b.add(feats, range(end_frame(WARM) + 10, fe_end + 30, 8), 0, "libri")
    print(f"[{split}] librispeech: {len(flacs[::args.libri_stride])} utt -> {len(b.y) - n0} windows", flush=True)

    for spec in (cfg.get("long_run_negatives", []) if split == "train" and args.long_negatives else []):
        n0 = len(b.y)
        nh, ng = add_long_run_negatives(b, spec, rng)
        print(f"[{split}] long-run negatives {pathlib.Path(spec['run_dir']).name} chunks {spec['chunks']}: "
              f"{nh} hard windows x{spec['hard_reps']}, {ng} general -> {len(b.y) - n0} windows", flush=True)

    for spec in (cfg.get(args.session_negatives, []) if split == "train" and args.session_negatives else []):
        n0 = len(b.y)
        nh, ng = add_session_negatives(b, spec)
        print(f"[{split}] session negatives {pathlib.Path(spec['run_dir']).name}: {nh} hard windows x{spec['hard_reps']}, "
              f"{ng} general -> {len(b.y) - n0} windows", flush=True)

    for rn in cfg.get(f"real_{split}_runs", []):
        n0 = len(b.y)
        nk = add_real_run(b, pathlib.Path(cfg["runs_root"]) / rn, rng, args.real_copies)
        print(f"[{split}] real {rn}: {nk} keywords -> {len(b.y) - n0} windows", flush=True)

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
    ap.add_argument("--real-copies", type=int, default=6)
    ap.add_argument("--long-negatives", action="store_true", help="add sources.json long_run_negatives (v3)")
    ap.add_argument("--extra-beds", default="", help="sources.json key with additional training bed files (v3: bed_train_night)")
    ap.add_argument("--tts-root", default="", help="override sources.json tts_root (e.g. ~/ps26172_data/tts_v2)")
    ap.add_argument("--continuation", type=float, default=0.0,
                    help="v4: share of TTS positive streams followed by 0.5-1.5 s of speech after a 0-250 ms gap")
    ap.add_argument("--session-negatives", default="",
                    help="v4: sources.json key with multi-session long-run negatives (active household)")
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
