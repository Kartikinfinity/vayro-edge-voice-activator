"""Host twin of the firmware front end: ctypes over libpsfe.so, built from the same C sources.

    from model.frontend.psfe import Frontend
    fe = Frontend()                    # reads model/frontend.json
    feats = fe.features(int16_audio)   # (frames, 40) uint16, identical to the device
    q = fe.to_int8(feats)              # model input mapping from frontend.json
"""
import ctypes
import hashlib
import json
import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
JSON = HERE.parent / "frontend.json"


class _Params(ctypes.Structure):
    _fields_ = [
        ("sample_rate_hz", ctypes.c_int), ("window_ms", ctypes.c_int), ("hop_ms", ctypes.c_int),
        ("mel_bands", ctypes.c_int), ("mel_low_hz", ctypes.c_float), ("mel_high_hz", ctypes.c_float),
        ("fb_output_scale_shift", ctypes.c_int), ("nr_smoothing_bits", ctypes.c_int),
        ("nr_even_smoothing", ctypes.c_float), ("nr_odd_smoothing", ctypes.c_float),
        ("nr_min_signal_remaining", ctypes.c_float), ("pcan_enable", ctypes.c_int),
        ("pcan_strength", ctypes.c_float), ("pcan_offset", ctypes.c_float), ("pcan_gain_bits", ctypes.c_int),
        ("log_enable", ctypes.c_int), ("log_scale_shift", ctypes.c_int),
    ]


class Frontend:
    def __init__(self, json_path=JSON, lib_path=HERE / "libpsfe.so"):
        raw = pathlib.Path(json_path).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        c = json.loads(raw)
        self.cfg = c
        self.bands = c["mel_bands"]
        self.hop = c["sample_rate_hz"] * c["hop_ms"] // 1000
        self.window = c["sample_rate_hz"] * c["window_ms"] // 1000
        self._p = _Params(
            c["sample_rate_hz"], c["window_ms"], c["hop_ms"], c["mel_bands"], c["mel_low_hz"], c["mel_high_hz"],
            c["filterbank_output_scale_shift"], c["noise_reduction"]["smoothing_bits"],
            c["noise_reduction"]["even_smoothing"], c["noise_reduction"]["odd_smoothing"],
            c["noise_reduction"]["min_signal_remaining"], c["pcan"]["enable"], c["pcan"]["strength"],
            c["pcan"]["offset"], c["pcan"]["gain_bits"], c["log_scale"]["enable"], c["log_scale"]["scale_shift"])
        self._lib = ctypes.CDLL(str(lib_path))
        self._lib.ps_fe_init.argtypes = [ctypes.POINTER(_Params)]
        self._lib.ps_fe_process_all.restype = ctypes.c_size_t
        self._lib.ps_fe_process_all.argtypes = [ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t,
                                                ctypes.POINTER(ctypes.c_uint16), ctypes.c_size_t]
        if self._lib.ps_fe_init(ctypes.byref(self._p)) != 0:
            raise RuntimeError("ps_fe_init failed")

    def reset(self):
        """Fresh state (noise estimate / PCAN) — as after device boot. Call before each independent clip."""
        self._lib.ps_fe_reset()

    def features(self, audio_int16: np.ndarray, reset: bool = True) -> np.ndarray:
        a = np.ascontiguousarray(audio_int16, dtype=np.int16)
        if reset:
            self.reset()
        max_frames = len(a) // self.hop + 1
        out = np.zeros((max_frames, self.bands), dtype=np.uint16)
        n = self._lib.ps_fe_process_all(a.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), len(a),
                                        out.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)), max_frames)
        return out[:n]

    @staticmethod
    def to_int8(feats: np.ndarray) -> np.ndarray:
        q = ((feats.astype(np.int32) * 256) + 333) // 666 - 128
        return np.clip(q, -128, 127).astype(np.int8)
