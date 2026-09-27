"""M2 golden-vector parity test (architecture §7.3): device front-end features vs host twin, bit-exact.

The device runs the front end on its live int16 stream and sends every feature frame; the host
recomputes features from the SAME int16 samples (audio_16bit.wav of that run) with the twin
built from the same C sources. PASS = every compared frame identical in all 40 bands, frame
boundaries identical, and the device's frontend.json SHA-256 equals the twin's.

Usage (WSL venv): python model/frontend/parity_test.py <run_dir>   -> <run_dir>/parity_report.json
"""
import json
import pathlib
import sys
import wave

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from model.frontend.psfe import Frontend  # noqa: E402


def main(run: pathlib.Path) -> int:
    summ = json.loads((run / "capture_summary.json").read_text(encoding="utf-8"))
    s0 = summ["sessions"][0]
    if s0["host_gap_count"]:
        print("run has host gaps; parity needs a gap-free stream")
        return 2
    with wave.open(str(run / "audio_16bit.wav")) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)

    fe = Frontend()
    bands = fe.bands
    rec = np.dtype([("frame", "<u4"), ("end", "<u4"), ("bands", "<u2"), ("v", "<u2", (bands,))])
    dev = np.fromfile(run / "features_device.bin", dtype=rec)
    cfg = [json.loads(line) for line in (run / "device_events.jsonl").read_text(encoding="utf-8").splitlines()]
    dev_sha = next((e.get("fe_sha256") for e in cfg if e.get("type") == "CFG" and "fe_sha256" in e), None)

    host = fe.features(audio)
    host_end = fe.window + fe.hop * np.arange(len(host))
    usable = dev[dev["end"] <= len(audio)]
    n = min(len(usable), len(host))
    d, h = usable[:n], host[:n]

    contiguous = bool(np.array_equal(d["frame"], np.arange(n)))
    ends_equal = bool(np.array_equal(d["end"], host_end[:n]))
    diff = d["v"].astype(np.int32) - h.astype(np.int32)
    bad_frames = np.where(np.any(diff != 0, axis=1))[0]
    report = {
        "run": run.name,
        "frontend_sha256_twin": fe.sha256,
        "frontend_sha256_device": dev_sha,
        "sha_match": dev_sha == fe.sha256,
        "audio_samples": int(len(audio)),
        "frames_compared": int(n),
        "frames_device_total": int(len(dev)),
        "frame_index_contiguous": contiguous,
        "frame_boundaries_equal": ends_equal,
        "frames_bit_exact": int(n - len(bad_frames)),
        "frames_mismatched": int(len(bad_frames)),
        "values_mismatched": int(np.count_nonzero(diff)),
        "max_abs_diff": int(np.abs(diff).max()) if n else None,
        "first_mismatch_frame": int(bad_frames[0]) if len(bad_frames) else None,
        "device_uint16_range": [int(d["v"].min()), int(d["v"].max())] if n else None,
    }
    report["PASS"] = bool(n > 0 and report["sha_match"] and contiguous and ends_equal and not len(bad_frames))
    (run / "parity_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["PASS"] else 1


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1])))
