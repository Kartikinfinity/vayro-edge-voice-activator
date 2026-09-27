"""M3 deployment parity: device int8 model outputs (posteriors_device.bin) vs the host running the SAME
.tflite with TFLite reference kernels on the host-twin features of the SAME audio. Also reports
device inference cycles from @STATS. Writes <run>/posterior_parity.json.

Usage (WSL venv): python model/eval/posterior_parity.py <run_dir> <model_int8.tflite>
"""
import json
import pathlib
import sys
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.eval.eval_stream import posteriors  # noqa: E402
from model.frontend.psfe import Frontend  # noqa: E402

run, model = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
with wave.open(str(run / "audio_16bit.wav")) as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
fe = Frontend()
host_feats = fe.to_int8(fe.features(audio))
_, _, ends, host_raw = posteriors(model, host_feats)
dev = np.fromfile(run / "posteriors_device.bin", dtype=np.dtype([("frame", "<u4"), ("raw", "i1"), ("trig", "u1")]))
host = dict(zip(ends.tolist(), host_raw.tolist()))
common = [(int(f), int(r)) for f, r in zip(dev["frame"], dev["raw"]) if int(f) in host]
diff = np.array([r - host[f] for f, r in common])
ev = [json.loads(x) for x in (run / "device_events.jsonl").read_text(encoding="utf-8").splitlines()]
stats = [e for e in ev if e["type"] == "PERF" and e.get("inf_cyc_mean")]
rep = {
    "run": run.name, "model": str(model), "inferences_compared": len(common),
    "raw_output_bit_exact": int(np.sum(diff == 0)), "raw_output_mismatched": int(np.sum(diff != 0)),
    "max_abs_raw_diff": int(np.abs(diff).max()) if len(diff) else None,
    "note": "host features come from the host twin; any feature-level mismatch (M2) propagates here",
    "device_inference_cycles_mean_of_1s_means": round(float(np.mean([e["inf_cyc_mean"] for e in stats])), 0) if stats else None,
    "device_inference_cycles_max": int(max(e["inf_cyc_max"] for e in stats)) if stats else None,
    "device_frontend_cycles_mean": round(float(np.mean([e["fe_cyc_mean"] for e in stats])), 0) if stats else None,
    "device_triggers": int(dev["trig"].sum()),
}
if stats:
    inf_rate = 100.0 / 6.0  # inferences per second at stride 6 frames
    rep["est_inference_cpu_pct_one_core_240MHz"] = round(rep["device_inference_cycles_mean_of_1s_means"] * inf_rate / 240e6 * 100, 2)
    rep["est_frontend_cpu_pct_one_core_240MHz"] = round(rep["device_frontend_cycles_mean"] * 100 / 240e6 * 100, 2)
(run / "posterior_parity.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
print(json.dumps(rep, indent=2))
