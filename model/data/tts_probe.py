"""Pronunciation probe: which spelling makes each Piper voice say "Hey VAI-ro"?
Prints espeak-ng phonemes per spelling and writes one WAV per (voice, spelling) for a human listening check.
Output: model/data/tts_probe/  (not training data)."""
import pathlib
import wave

from piper import PiperVoice

VOICES = pathlib.Path.home() / "ps26172_data" / "piper_voices"
OUT = pathlib.Path(__file__).resolve().parent / "tts_probe"
OUT.mkdir(exist_ok=True)
SPELLINGS = {
    "en": ["Hey Vayro", "Hey Vyro", "Hey Viro", "Hey Vairo", "Hey Vyeroh"],
    "hi": ["हे वाइरो", "हे वायरो", "हे वैरो"],
}
for onnx in sorted(VOICES.glob("*.onnx")):
    voice = PiperVoice.load(str(onnx))
    lang = "hi" if onnx.name.startswith("hi_") else "en"
    print(f"== {onnx.stem}  speakers={voice.config.num_speakers}")
    for i, text in enumerate(SPELLINGS[lang]):
        ph = voice.phonemize(text)
        print(f"   {text!r:16} -> {' | '.join(''.join(s) for s in ph)}")
        with wave.open(str(OUT / f"{onnx.stem}__{i}.wav"), "wb") as w:
            voice.synthesize_wav(text, w)
