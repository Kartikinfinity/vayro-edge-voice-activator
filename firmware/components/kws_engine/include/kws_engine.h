/* SS-4 · kws_engine — TFLite Micro interpreter (esp-tflite-micro + esp-nn) running the int8
 * windowed keyword model (DEC-11). Weights stay in flash; the tensor arena is static internal RAM. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const char *run;
    const char *model_sha256;
    size_t model_bytes;
    size_t arena_bytes;
    size_t arena_used_bytes;
    int win_frames;
    int bands;
} kws_info_t;

/* Fails with ESP_ERR_INVALID_VERSION if the model was trained with a different frontend.json. */
esp_err_t kws_init(kws_info_t *info);

/* window: win_frames x bands front-end int8 features, oldest first.
 * Returns the posterior; *raw = model int8 output; *cycles = CPU cycles of Invoke(). */
float kws_infer(const int8_t *window, int8_t *raw, uint32_t *cycles);

/* Zero-copy variant (EXP-1: saves the separate 4 KB window buffer): write each of the win_frames rows
 * (front-end int8 features, oldest first) straight into the model input tensor, then invoke. */
void kws_set_row(int row, const int8_t *features);
float kws_invoke(int8_t *raw, uint32_t *cycles);

#ifdef __cplusplus
}
#endif
