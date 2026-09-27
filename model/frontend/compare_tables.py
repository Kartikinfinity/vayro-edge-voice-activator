"""Compare the device's init-time front-end table hashes (@FETAB in a run) with the host twin's."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from model.frontend.psfe import Frontend  # noqa: E402

run = pathlib.Path(sys.argv[1])
ev = [json.loads(x) for x in (run / "device_events.jsonl").read_text(encoding="utf-8").splitlines()]
dev = next(e for e in ev if e["type"] == "FETAB" and "names" in e)
applied = next((e.get("canonical_tables_applied") for e in ev if e["type"] == "FETAB" and "canonical_tables_applied" in e), None)
print(f"canonical_tables_applied on device: {applied}")
names, dh = dev["names"].split(","), dev["hashes"].split(",")
hh = Frontend().table_hashes()
result = {n: {"device": d, "host": h, "equal": d == h} for n, d, h in zip(names, dh, hh)}
(run / "fetab_compare.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
for n, r in result.items():
    print(f"{n:20} device {r['device']}  host {r['host']}  {'EQUAL' if r['equal'] else 'DIFFERENT'}")
