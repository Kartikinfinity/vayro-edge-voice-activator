"""Synthetic training audio with Piper TTS (DEC-14 spellings), split by VOICE/SPEAKER.

Positives: "Hey Vyro" / "हे वाइरो" with random speaker, speed (length_scale), and prosody noise.
Negatives: partial keyword ("Hey", "Vyro"), phonetic confusables, and common short phrases.
Output: ~/ps26172_data/tts/{pos,neg}/*.wav (native voice rate) + manifest.csv. Seeded, reproducible.

Split rule (speaker-disjoint, X15): per multi-speaker voice, the last ~12 % of speaker IDs are VAL;
the single-speaker Hindi voice is TRAIN only. Real recordings (kw_S0x) are never mixed in here.
"""
import argparse
import csv
import pathlib
import random
import time
import wave

from piper import PiperVoice, SynthesisConfig

VOICES_DIR = pathlib.Path.home() / "ps26172_data" / "piper_voices"
OUT = pathlib.Path.home() / "ps26172_data" / "tts"

POS_EN = ["Hey Vyro", "Hey, Vyro", "Hey Vyro!", "hey vyro.", "Hey Vyro?"]
POS_HI = ["हे वाइरो", "हे, वाइरो", "हे वाइरो!"]
NEG_EN = ["Hey", "Vyro", "Hey there", "Hey you", "Hey bro", "Hey guys", "Hey buddy", "Hey wait",
          "Hero", "Cairo", "Viral", "Wire", "Fire", "Buyer", "Higher", "Tyre", "Pyro", "Via", "Okay",
          "Hey hero", "Hey Cairo", "Hey Vayu", "Hey Ravi", "Hey Viral", "Hey Vivo", "Hey Vijay",
          "Hey Mira", "Hey Rohit", "Hi there", "Why so", "I will go", "Hey Tyrone", "Hey, why not",
          "Hey Vinay", "Hey Irene", "Hey Byron", "Hey Myra", "hey, hi, hello", "Very good", "Hey Viraj"]
NEG_HI = ["हे", "वायु", "हेलो", "हे राम", "वाह", "हे भाई", "हे वायु", "वीरू", "हीरो"]

# v2 additions — driven by live-device false activations in session kw_S01_s2 (v0 fired on "Hey" alone,
# "Hey Vayu", "Hey bro", "Hero", "Pyro"): many "Hey + X" phrases and "V-ai"/"-ro" neighbours.
NEG_EN_V2 = NEG_EN + [
    "Hey", "Hey", "Hey!", "Hey, hey", "Hey Vayu", "Hey Vayu!", "Vayu", "Hey bro", "Hey hero", "Hey Pyro", "Pyro",
    "Hey Rio", "Hey Tyro", "Hey Biro", "Hey Kiro", "Hey Miro", "Hey Nero", "Hey Zero", "Hey Cairo", "Hey Vinay",
    "Hey Varun", "Hey Vivek", "Hey Vikram", "Hey Vaibhav", "Hey Vishal", "Hey Arjun", "Hey Rahul", "Hey Priya",
    "Hey Maya", "Hey Riya", "Hey Aryan", "Hey Karan", "Hey Neha", "Hey Pooja", "Hey Rohan", "Hey Siya",
    "Hey, why?", "Hey, buy it", "Hey, I know", "Hey, how are you", "Hey, what's up", "Hey there, hi",
    "Hey Viraj", "Hey Viren", "Hey Vyas", "Hey Vijay", "Vaio", "Wire", "Viral", "Vero", "Byron", "Tyrone",
    "Why row", "Vai", "Hey wait a minute", "Hey look at this", "Hey come here", "Hey stop",
]
NEG_HI_V2 = NEG_HI + ["हे", "हे", "हे वायु", "वायु", "हे भाई", "हे यार", "हे विजय", "हे रवि", "हे हीरो", "पायरो"]

# voice -> (n_pos, n_neg); speaker count read from the voice config
PLAN = {
    "en_US-libritts_r-medium": (1400, 1100),
    "en_GB-vctk-medium": (400, 300),
    "en_US-l2arctic-medium": (300, 250),
    "hi_IN-pratham-medium": (120, 90),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="multiply clip counts (quick tests)")
    ap.add_argument("--seed", type=int, default=26172)
    ap.add_argument("--version", default="v1", choices=["v1", "v2"],
                    help="v2: faster positives (real S01 utterances measured 0.42-0.78 s vs TTS median 0.79 s) "
                         "and the expanded confusable list")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = pathlib.Path(args.out).expanduser()
    speed = (0.6, 1.2) if args.version == "v2" else (0.8, 1.35)
    neg_en, neg_hi = (NEG_EN_V2, NEG_HI_V2) if args.version == "v2" else (NEG_EN, NEG_HI)
    plan = {k: (p, int(n * (1.8 if args.version == "v2" else 1))) for k, (p, n) in PLAN.items()}
    rng = random.Random(args.seed)
    for d in ("pos", "neg"):
        (out / d).mkdir(parents=True, exist_ok=True)
    rows = []
    t0 = time.time()
    for vname, (n_pos, n_neg) in plan.items():
        voice = PiperVoice.load(str(VOICES_DIR / f"{vname}.onnx"))
        n_spk = max(1, voice.config.num_speakers)
        n_val = 0 if n_spk == 1 else max(1, round(n_spk * 0.12))
        hindi = vname.startswith("hi_")
        for label, n, texts in (("pos", n_pos, POS_HI if hindi else POS_EN), ("neg", n_neg, neg_hi if hindi else neg_en)):
            for i in range(int(n * args.scale)):
                spk = rng.randrange(n_spk)
                cfg = SynthesisConfig(speaker_id=spk if n_spk > 1 else None,
                                      length_scale=rng.uniform(*speed),
                                      noise_scale=rng.uniform(0.45, 0.9),
                                      noise_w_scale=rng.uniform(0.5, 1.0))
                text = rng.choice(texts)
                name = f"{label}_{vname}_{i:05d}.wav"
                with wave.open(str(out / label / name), "wb") as w:
                    voice.synthesize_wav(text, w, syn_config=cfg)
                rows.append({"file": f"{label}/{name}", "label": label, "voice": vname, "speaker": spk, "text": text,
                             "length_scale": round(cfg.length_scale, 3), "noise_scale": round(cfg.noise_scale, 3),
                             "noise_w_scale": round(cfg.noise_w_scale, 3),
                             "split": "val" if spk >= n_spk - n_val else "train"})
        print(f"{vname}: done, {len(rows)} clips total, {time.time() - t0:.0f} s", flush=True)
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} clips in {time.time() - t0:.0f} s -> {out}")


if __name__ == "__main__":
    main()
