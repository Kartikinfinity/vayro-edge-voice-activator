"""Stream integrity: each server-received activation WAV must be a bit-exact excerpt of the device's own int16 stream
(USB capture of the same session). Locates each stream by exact-match search and reports mismatches.
Usage: python server/stream_integrity.py <capture_run_dir> <server_session_dir> [wav_glob, default *act*.wav]
(server WAVs are named c<HHMMSS>_act<N>.wav since 28 Sep; pass e.g. c192732_act*.wav to select one connection)"""
import glob
import json
import pathlib
import sys
import wave

import numpy as np

cap = pathlib.Path(sys.argv[1])
srv = pathlib.Path(sys.argv[2])
with wave.open(str(cap / "audio_16bit.wav")) as w:
    ref = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
res = []
pat = sys.argv[3] if len(sys.argv) > 3 else "*act*.wav"
for p in sorted(srv.glob(pat)):
    with wave.open(str(p)) as w:
        s = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    # candidate offsets: positions where the first 64 samples match exactly
    probe = s[:64]
    cand = np.where(ref[: len(ref) - len(s)] == probe[0])[0]
    hit = None
    for c in cand:
        if np.array_equal(ref[c:c + 64], probe):
            hit = int(c)
            break
    if hit is None:
        res.append({"file": p.name, "located": False})
        continue
    seg = ref[hit:hit + len(s)]
    mism = int(np.count_nonzero(seg != s))
    res.append({"file": p.name, "located": True, "offset_s": round(hit / 16000, 3), "samples": int(len(s)),
                "mismatched_samples": mism, "bit_exact": mism == 0})
ok = sum(r.get("bit_exact", False) for r in res)
print(json.dumps({"streams": len(res), "bit_exact": ok, "results": res[:30]}, indent=1))
(srv / f"stream_integrity_{pat.split('_')[0].strip('*') or 'all'}.json").write_text(json.dumps({"capture": cap.name, "streams": len(res), "bit_exact": ok,
                                                      "results": res}, indent=2), encoding="utf-8")
