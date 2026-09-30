"""Repository integrity checks that need no toolchain (run by .github/workflows/ci.yml and by hand).

They verify that the files which must agree with each other still do:
  1. the front-end definition (model/frontend.json) and the three places its SHA-256 is recorded:
     the firmware header, the canonical front-end tables and the embedded model;
  2. the embedded model (firmware/components/kws_engine/model_data.c) is byte-for-byte the shipped
     model/artifacts/<run>/model_int8.tflite, with the SHA-256 recorded in its metrics.json;
  3. the compiled-in operating point (firmware/sdkconfig.model) equals the recorded ship decision
     (model/artifacts/selection_final.json);
  4. the pinned firmware dependencies are still the ones in the SBOM.

Usage: python tools/ci_checks.py          (exit code 1 on any mismatch)
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
failures = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not ok:
        failures.append(name)


def c_string(text, symbol):
    m = re.search(rf'{symbol}\[\]\s*=\s*"([^"]*)"', text)
    return m.group(1) if m else None


# 1. front-end definition
fe_sha = hashlib.sha256((ROOT / "model" / "frontend.json").read_bytes()).hexdigest()
header = (ROOT / "firmware/components/microfrontend/include/ps_frontend_config.h").read_text(encoding="utf-8")
tables = (ROOT / "firmware/components/microfrontend/ps_frontend_tables.c").read_text(encoding="utf-8")
model_c = (ROOT / "firmware/components/kws_engine/model_data.c").read_text(encoding="utf-8")
header_sha = re.search(r'PS_FE_JSON_SHA256 "([0-9a-f]{64})"', header)
check("frontend.json SHA-256 == firmware header", bool(header_sha) and header_sha.group(1) == fe_sha, fe_sha[:16])
check("frontend.json SHA-256 == canonical tables", c_string(tables, "ps_fe_tables_fe_sha256") == fe_sha)
check("frontend.json SHA-256 == embedded model's training front end", c_string(model_c, "g_kws_model_fe_sha256") == fe_sha)

# 2. embedded model
run = c_string(model_c, "g_kws_model_run")
art = ROOT / "model" / "artifacts" / str(run)
tflite = (art / "model_int8.tflite").read_bytes()
metrics = json.loads((art / "metrics.json").read_text(encoding="utf-8"))
sha = hashlib.sha256(tflite).hexdigest()
check(f"model artefact {run}: SHA-256 == metrics.json", sha == metrics["tflite_sha256"], sha[:16])
check("embedded model SHA-256 == artefact", c_string(model_c, "g_kws_model_sha256") == sha)
length = re.search(r"g_kws_model_len\s*=\s*(\d+)", model_c)
check("embedded model length == artefact", bool(length) and int(length.group(1)) == len(tflite), f"{len(tflite)} B")
body = re.search(r"g_kws_model\[\]\s*=\s*\{([^}]*)\}", model_c)
check("embedded model bytes == artefact bytes",
      bool(body) and bytes(int(v) for v in body.group(1).split(",")) == tflite)
check("model uses only the five registered operators",
      sorted(metrics["ops"]) == ["CONV_2D", "DEPTHWISE_CONV_2D", "FULLY_CONNECTED", "LOGISTIC", "RESHAPE"])

# 3. operating point
shipped = json.loads((ROOT / "model/artifacts/selection_final.json").read_text(encoding="utf-8"))["shipped"]
cfg = dict(re.findall(r"^(CONFIG_PS_KWS_\w+)=(\d+)$", (ROOT / "firmware/sdkconfig.model").read_text(encoding="utf-8"), re.M))
check("shipped model == embedded model", shipped["model"] == run, f"{shipped['model']} / {run}")
check("sdkconfig.model == ship decision",
      cfg.get("CONFIG_PS_KWS_THRESHOLD_PCT") == str(round(shipped["threshold"] * 100))
      and cfg.get("CONFIG_PS_KWS_AVG_N") == str(shipped["N"])
      and cfg.get("CONFIG_PS_KWS_STRIDE_FRAMES") == str(shipped["stride_frames"])
      and cfg.get("CONFIG_PS_KWS_REFRACTORY_MS") == str(round(shipped["refractory_s"] * 1000)), str(cfg))

# 4. pinned dependencies
lock = (ROOT / "firmware/dependencies.lock").read_text(encoding="utf-8")
sbom = (ROOT / "docs/SBOM.md").read_text(encoding="utf-8")
for comp in ("esp-tflite-micro", "esp-nn"):
    m = re.search(rf"espressif/{comp}:.*?\n\s+version: ([\d.]+)", lock, re.S)
    check(f"{comp} pinned and listed in the SBOM", bool(m) and re.search(rf"{comp} \| {re.escape(m.group(1))} \|", sbom) is not None,
          m.group(1) if m else "not pinned")

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
