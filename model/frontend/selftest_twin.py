"""Smoke test for the host twin (not evidence): runs, shapes, determinism, reset behaviour."""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from model.frontend.psfe import Frontend  # noqa: E402

fe = Frontend()
x = np.random.default_rng(0).normal(0, 300, 16000).astype(np.int16)
f1 = fe.features(x)
f2 = fe.features(x)
print("frontend.json sha256", fe.sha256[:16], "| frames", f1.shape, "| expected", (16000 - fe.window) // fe.hop + 1)
print("uint16 range", int(f1.min()), int(f1.max()), "| int8 range", int(fe.to_int8(f1).min()), int(fe.to_int8(f1).max()))
print("deterministic with reset:", bool(np.array_equal(f1, f2)))
