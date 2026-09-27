/* SS-3 · frontend — thin wrapper over the vendored TFLM microfrontend.
 *
 * The SAME C sources build the firmware front end and the host twin (model/frontend/),
 * so train/deploy features are bit-identical by construction and checked by the parity test.
 * Firmware fills ps_fe_params_t from ps_frontend_config.h; the host fills it from frontend.json.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int sample_rate_hz;
    int window_ms;
    int hop_ms;
    int mel_bands;
    float mel_low_hz;
    float mel_high_hz;
    int fb_output_scale_shift;
    int nr_smoothing_bits;
    float nr_even_smoothing;
    float nr_odd_smoothing;
    float nr_min_signal_remaining;
    int pcan_enable;
    float pcan_strength;
    float pcan_offset;
    int pcan_gain_bits;
    int log_enable;
    int log_scale_shift;
} ps_fe_params_t;

/* Returns 0 on success. Allocates the microfrontend state from the heap (once). */
int ps_fe_init(const ps_fe_params_t *p);
void ps_fe_reset(void);

/* Feeds samples; writes at most one feature frame. Returns 1 if a frame was produced (out filled
 * with mel_bands uint16 values), 0 otherwise. *consumed = samples used; call again with the rest. */
int ps_fe_process(const int16_t *samples, size_t n, size_t *consumed, uint16_t *out);

/* Runs a whole buffer through the front end (host twin / offline use). Returns frames written. */
size_t ps_fe_process_all(const int16_t *samples, size_t n, uint16_t *out, size_t max_frames);

/* micro_speech FeatureProvider mapping, see frontend.json "int8_mapping". */
static inline int8_t ps_fe_to_int8(uint16_t v)
{
    int32_t q = (((int32_t)v * 256) + 333) / 666 - 128;
    return (int8_t)(q < -128 ? -128 : (q > 127 ? 127 : q));
}

#ifdef __cplusplus
}
#endif
