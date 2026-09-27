"""Environment check: is the int8 TFLite converter usable in this TF build? (not evidence)"""
import numpy as np
import tensorflow as tf

print("tf", tf.__version__, "| keras", tf.keras.__version__ if hasattr(tf.keras, "__version__") else "?")
print("tf.lite.TFLiteConverter present:", hasattr(tf.lite, "TFLiteConverter"))
inp = tf.keras.Input((100, 1, 40))
x = tf.keras.layers.Conv2D(8, (3, 1), strides=(2, 1))(inp)
x = tf.keras.layers.DepthwiseConv2D((3, 1))(x)
x = tf.keras.layers.GlobalAveragePooling2D()(x)
out = tf.keras.layers.Dense(1, activation="sigmoid")(x)
m = tf.keras.Model(inp, out)
conv = tf.lite.TFLiteConverter.from_keras_model(m)
conv.optimizations = [tf.lite.Optimize.DEFAULT]
conv.representative_dataset = lambda: ([np.random.rand(1, 100, 1, 40).astype(np.float32)] for _ in range(20))
conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
conv.inference_input_type = tf.int8
conv.inference_output_type = tf.int8
b = conv.convert()
it = tf.lite.Interpreter(model_content=b)
ops = sorted({d["op_name"] for d in it._get_ops_details()})
print("int8 model bytes", len(b), "| ops", ops)
