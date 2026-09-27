"""Train the windowed causal DS-CNN keyword model (Architecture A family, DEC-11) and export int8 TFLite.

Input: WIN x 1 x 40 int8 features from build_dataset.py, fed as q/128. Random initialisation only
(no pre-trained weights anywhere — provenance requirement R6). Output: model/artifacts/<run>/.

Usage (WSL venv): python model/train/train.py --data ~/ps26172_data/ds_v0 --run v0
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import time

import numpy as np
import tensorflow as tf

ROOT = pathlib.Path(__file__).resolve().parents[2]
L = tf.keras.layers


def build_model(win=100, bands=40, batch_size=None):
    """No padding anywhere (valid convs): windowed and future streaming execution stay equivalent (X5).
    batch_size=1 builds the static device graph used for export (model/train/export.py)."""
    inp = tf.keras.Input((win, 1, bands), batch_size=batch_size, name="features")

    def cbr(x, layer):
        x = layer(x)
        x = L.BatchNormalization()(x)
        return L.ReLU()(x)

    x = cbr(inp, L.Conv2D(24, (3, 1), strides=(2, 1), use_bias=False))
    for k, s, w in ((5, 2, 32), (5, 1, 32), (5, 2, 48), (3, 1, 48)):
        # (s, s): TF's CPU depthwise kernel needs equal strides; width is 1 with kernel width 1, so this is
        # identical to (s, 1) (output width stays 1).
        x = cbr(x, L.DepthwiseConv2D((k, 1), strides=(s, s), use_bias=False))
        x = cbr(x, L.Conv2D(w, (1, 1), use_bias=False))
    x = L.Reshape((x.shape[1] * x.shape[2] * x.shape[3],))(x)  # static shape -> a single RESHAPE op
                                                               # (Flatten emitted SHAPE/STRIDED_SLICE/PACK)
    x = L.Dropout(0.25)(x)
    out = L.Dense(1, activation="sigmoid", name="p_keyword")(x)
    return tf.keras.Model(inp, out)


def macs(model):
    total = 0
    for layer in model.layers:
        if isinstance(layer, (L.Conv2D, L.DepthwiseConv2D, L.Dense)):
            o = layer.output.shape
            if isinstance(layer, L.Dense):
                total += layer.kernel.shape[0] * layer.kernel.shape[1]
            elif isinstance(layer, L.DepthwiseConv2D):
                total += o[1] * o[2] * o[3] * layer.kernel_size[0] * layer.kernel_size[1]
            else:
                total += o[1] * o[2] * o[3] * layer.kernel_size[0] * layer.kernel_size[1] * layer.input.shape[-1]
    return int(total)


def load(path):
    d = np.load(path)
    return d["x"][:, :, None, :], d["y"].astype(np.float32), d["src"]


def augment(x, y):
    """SpecAugment-style masks on the int8-derived float features (train only)."""
    x = tf.identity(x)
    f0 = tf.random.uniform([], 0, 37, dtype=tf.int32)
    fw = tf.random.uniform([], 0, 4, dtype=tf.int32)
    fmask = tf.logical_or(tf.range(40) < f0, tf.range(40) >= f0 + fw)
    t0 = tf.random.uniform([], 0, 92, dtype=tf.int32)
    tw = tf.random.uniform([], 0, 8, dtype=tf.int32)
    tmask = tf.logical_or(tf.range(100) < t0, tf.range(100) >= t0 + tw)
    m = tf.cast(tmask[:, None, None], x.dtype) * tf.cast(fmask[None, None, :], x.dtype)
    return x * m + (-1.0) * (1.0 - m), y  # masked cells -> feature floor (q = -128)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr", type=float, default=1e-3, help="v0 used 3e-3: val metrics oscillated (BatchNorm stats lag)")
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--pos-weight", type=float, default=0.0, help="0 = balanced")
    ap.add_argument("--seed", type=int, default=26172)
    args = ap.parse_args()
    tf.keras.utils.set_random_seed(args.seed)
    data = pathlib.Path(args.data).expanduser()
    out = ROOT / "model" / "artifacts" / args.run
    out.mkdir(parents=True, exist_ok=True)

    xtr, ytr, _ = load(data / "train.npz")
    xva, yva, sva = load(data / "val.npz")
    npos, nneg = ytr.sum(), len(ytr) - ytr.sum()
    wpos = args.pos_weight or float(nneg / npos)
    print(f"train {len(ytr)} (pos {int(npos)}), val {len(yva)} (pos {int(yva.sum())}), pos weight {wpos:.2f}")

    # Keep int8 in memory (the train set is ~0.7 GB as int8, ~2.9 GB as float32); scale per element.
    to_f = lambda x, y: (tf.cast(x, tf.float32) / 128.0, y)  # noqa: E731
    ds = (tf.data.Dataset.from_tensor_slices((xtr, ytr))
          .shuffle(len(ytr), seed=args.seed).map(to_f, num_parallel_calls=4).map(augment, num_parallel_calls=4)
          .batch(args.batch).prefetch(4))
    vds = tf.data.Dataset.from_tensor_slices((xva, yva)).map(to_f).batch(1024)

    model = build_model()
    steps = int(np.ceil(len(ytr) / args.batch)) * args.epochs
    model.compile(optimizer=tf.keras.optimizers.Adam(tf.keras.optimizers.schedules.CosineDecay(args.lr, steps)),
                  loss="binary_crossentropy",
                  metrics=[tf.keras.metrics.AUC(name="auc"), tf.keras.metrics.AUC(name="pr_auc", curve="PR")])
    t0 = time.time()
    hist = model.fit(ds, validation_data=vds, epochs=args.epochs, class_weight={0: 1.0, 1: wpos},
                     callbacks=[tf.keras.callbacks.EarlyStopping("val_pr_auc", mode="max", patience=args.patience,
                                                                 restore_best_weights=True)], verbose=2)
    train_s = time.time() - t0
    model.save(out / "model.keras")

    # Full-int8 post-training quantisation; representative data = balanced training windows.
    rng = np.random.default_rng(args.seed)
    rep_idx = np.concatenate([rng.choice(np.where(ytr == 1)[0], 250, replace=False),
                              rng.choice(np.where(ytr == 0)[0], 250, replace=False)])
    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = lambda: ([xtr[i:i + 1].astype(np.float32) / 128.0] for i in rep_idx)
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8
    conv.inference_output_type = tf.int8
    tfl = conv.convert()
    (out / "model_int8.tflite").write_bytes(tfl)

    it = tf.lite.Interpreter(model_content=tfl)
    it.allocate_tensors()
    ind, outd = it.get_input_details()[0], it.get_output_details()[0]
    (isc, izp), (osc, ozp) = ind["quantization"], outd["quantization"]
    p_int8 = []
    for i in range(len(xva)):
        q = np.clip(np.round(xva[i:i + 1] / 128.0 / isc + izp), -128, 127).astype(np.int8)
        it.set_tensor(ind["index"], q)
        it.invoke()
        p_int8.append((it.get_tensor(outd["index"]).astype(np.float32)[0, 0] - ozp) * osc)
    p_int8 = np.array(p_int8)
    p_f = model.predict(vds.map(lambda x, y: x), verbose=0)[:, 0]

    def fr_at(p, fa_rate):
        thr = np.quantile(p[yva == 0], 1 - fa_rate)
        return float(np.mean(p[yva == 1] < thr)), float(thr)

    metrics = {
        "run": args.run, "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tensorflow": tf.__version__, "params": int(model.count_params()), "macs_per_inference": macs(model),
        "tflite_int8_bytes": len(tfl), "tflite_sha256": hashlib.sha256(tfl).hexdigest(),
        "ops": sorted({d["op_name"] for d in it._get_ops_details()}),
        "input_quant": [float(isc), int(izp)], "output_quant": [float(osc), int(ozp)],
        "train_windows": int(len(ytr)), "train_pos": int(npos), "val_windows": int(len(yva)), "val_pos": int(yva.sum()),
        "epochs_run": len(hist.history["loss"]), "train_seconds": round(train_s, 1),
        "val_window_metrics_NOTE": "per-window, not per-utterance; not FA/h — see eval_stream.py for stream metrics",
        "val_float_vs_int8_max_abs_prob_diff": float(np.max(np.abs(p_f - p_int8))),
        "val_int8_frr_at_window_fpr": {str(r): fr_at(p_int8, r) for r in (1e-2, 1e-3)},
        "data_meta": json.loads((data / "meta.json").read_text()),
        "history": {k: [round(float(v), 5) for v in vs] for k, vs in hist.history.items()},
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("params", "macs_per_inference", "tflite_int8_bytes", "ops", "epochs_run",
                                                "train_seconds", "val_float_vs_int8_max_abs_prob_diff",
                                                "val_int8_frr_at_window_fpr")}, indent=2))


if __name__ == "__main__":
    main()
