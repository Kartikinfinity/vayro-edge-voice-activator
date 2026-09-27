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
    args = ap.parse_args()
    rng = random.Random(args.seed)
    for d in ("pos", "neg"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
    rows = []
    t0 = time.time()
    for vname, (n_pos, n_neg) in PLAN.items():
        voice = PiperVoice.load(str(VOICES_DIR / f"{vname}.onnx"))
        n_spk = max(1, voice.config.num_speakers)
        n_val = 0 if n_spk == 1 else max(1, round(n_spk * 0.12))
        hindi = vname.startswith("hi_")
        for label, n, texts in (("pos", n_pos, POS_HI if hindi else POS_EN), ("neg", n_neg, NEG_HI if hindi else NEG_EN)):
            for i in range(int(n * args.scale)):
                spk = rng.randrange(n_spk)
                cfg = SynthesisConfig(speaker_id=spk if n_spk > 1 else None,
                                      length_scale=rng.uniform(0.8, 1.35),
                                      noise_scale=rng.uniform(0.45, 0.9),
                                      noise_w_scale=rng.uniform(0.5, 1.0))
                text = rng.choice(texts)
                name = f"{label}_{vname}_{i:05d}.wav"
                with wave.open(str(OUT / label / name), "wb") as w:
                    voice.synthesize_wav(text, w, syn_config=cfg)
                rows.append({"file": f"{label}/{name}", "label": label, "voice": vname, "speaker": spk, "text": text,
                             "length_scale": round(cfg.length_scale, 3), "noise_scale": round(cfg.noise_scale, 3),
                             "noise_w_scale": round(cfg.noise_w_scale, 3),
                             "split": "val" if spk >= n_spk - n_val else "train"})
        print(f"{vname}: done, {len(rows)} clips total, {time.time() - t0:.0f} s", flush=True)
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} clips in {time.time() - t0:.0f} s -> {OUT}")


if __name__ == "__main__":
    main()
