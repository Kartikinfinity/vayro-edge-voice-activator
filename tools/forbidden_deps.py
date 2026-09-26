"""X25 gate (architecture §6.3, §B9): fail if any proprietary / vendor voice-activation SDK or
pre-trained wake-word model is referenced anywhere in the repository or its managed components.

Run automatically by tools/idf.ps1 before every firmware build. Exit code 1 = violation.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
FORBIDDEN = re.compile(
    r"esp[-_]sr\b|wakenet|multinet|srmodels\.bin|picovoice|porcupine|pvporcupine|"
    r"sensory|trulyhandsfree|cyberon|alango|okay_nabu|hey_jarvis|hey_mycroft|alexa\.tflite",
    re.IGNORECASE,
)
SCAN_SUFFIXES = {".yml", ".yaml", ".lock", ".txt", ".cmake", ".c", ".cc", ".cpp", ".h", ".py", ".json", ".ini", ".csv"}
SKIP_DIRS = {".git", ".venv-host", "evidence", "__pycache__"}
SELF = pathlib.Path(__file__).resolve()

hits = []
for p in ROOT.rglob("*"):
    if any(part in SKIP_DIRS or part.startswith("build") for part in p.relative_to(ROOT).parts[:-1]):
        continue
    if FORBIDDEN.search(p.name):
        hits.append(f"{p}: forbidden name")
    if p.is_file() and p.suffix.lower() in SCAN_SUFFIXES and p.resolve() != SELF:
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{p}:{n}: {line.strip()[:120]}")

if hits:
    print("FORBIDDEN DEPENDENCY GATE: FAIL (X25)")
    print("\n".join(hits))
    sys.exit(1)
print(f"forbidden_deps: PASS ({ROOT})")
