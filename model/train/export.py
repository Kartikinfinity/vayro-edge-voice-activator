"""Full-int8 export with a STATIC batch of 1 (device graph), from a trained model.keras.

Keras 3 Reshape keeps a dynamic batch dimension, which the converter lowers to SHAPE/STRIDED_SLICE/PACK
+ RESHAPE. Rebuilding the same architecture with batch_size=1 and copying the weights yields a graph of
CONV_2D / DEPTHWISE_CONV_2D / RESHAPE / FULLY_CONNECTED / LOGISTIC only. Calibration data and seed are
the same as in train.py, so quantisation parameters are reproducible.

Usage (WSL venv): python model/train/export.py --run v0 --data ~/ps26172_data/ds_v0
"""
import argparse
import hashlib
import json
import pathlib
import sys

import numpy as np
import tensorflow as tf

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from model.train.train import build_model  # noqa: E402


def export_int8(model, xtr_i8, ytr, seed):
    static = build_model(batch_size=1)
    static.set_weights(model.get_weights())
    rng = np.random.default_rng(seed)
    rep_idx = np.concatenate([rng.choice(np.where(ytr == 1)[0], 250, replace=False),
                              rng.choice(np.where(ytr == 0)[0], 250, replace=False)])
    conv = tf.lite.TFLiteConverter.from_keras_model(static)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = lambda: ([xtr_i8[i:i + 1].astype(np.float32) / 128.0] for i in rep_idx)
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8
    conv.inference_output_type = tf.int8
    return conv.convert()


def tflite_ops(tfl):
    it = tf.lite.Interpreter(model_content=tfl, experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
    return sorted({d["op_name"] for d in it._get_ops_details()}), it


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--seed", type=int, default=26172)
    args = ap.parse_args()
    art = ROOT / "model" / "artifacts" / args.run
    model = tf.keras.models.load_model(art / "model.keras")
    d = np.load(pathlib.Path(args.data).expanduser() / "train.npz")
    tfl = export_int8(model, d["x"][:, :, None, :], d["y"], args.seed)
    (art / "model_int8.tflite").write_bytes(tfl)
    ops, it = tflite_ops(tfl)
    it.allocate_tensors()
    ind, outd = it.get_input_details()[0], it.get_output_details()[0]
    m = json.loads((art / "metrics.json").read_text(encoding="utf-8"))
    m.update({"tflite_int8_bytes": len(tfl), "tflite_sha256": hashlib.sha256(tfl).hexdigest(), "ops": ops,
              "input_quant": [float(ind["quantization"][0]), int(ind["quantization"][1])],
              "output_quant": [float(outd["quantization"][0]), int(outd["quantization"][1])],
              "export": "static batch=1 (model/train/export.py)"})
    (art / "metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"{args.run}: {len(tfl)} B, ops {ops}, in {m['input_quant']}, out {m['output_quant']}")


if __name__ == "__main__":
    main()
