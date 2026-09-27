#include "ps_frontend.h"

#include <string.h>

#include "tensorflow/lite/experimental/microfrontend/lib/frontend.h"
#include "tensorflow/lite/experimental/microfrontend/lib/frontend_util.h"

static struct FrontendState s_state;
static int s_ready;

int ps_fe_init(const ps_fe_params_t *p)
{
    struct FrontendConfig c;
    FrontendFillConfigWithDefaults(&c);
    c.window.size_ms = p->window_ms;
    c.window.step_size_ms = p->hop_ms;
    c.filterbank.num_channels = p->mel_bands;
    c.filterbank.lower_band_limit = p->mel_low_hz;
    c.filterbank.upper_band_limit = p->mel_high_hz;
    c.filterbank.output_scale_shift = p->fb_output_scale_shift;
    c.noise_reduction.smoothing_bits = p->nr_smoothing_bits;
    c.noise_reduction.even_smoothing = p->nr_even_smoothing;
    c.noise_reduction.odd_smoothing = p->nr_odd_smoothing;
    c.noise_reduction.min_signal_remaining = p->nr_min_signal_remaining;
    c.pcan_gain_control.enable_pcan = p->pcan_enable;
    c.pcan_gain_control.strength = p->pcan_strength;
    c.pcan_gain_control.offset = p->pcan_offset;
    c.pcan_gain_control.gain_bits = p->pcan_gain_bits;
    c.log_scale.enable_log = p->log_enable;
    c.log_scale.scale_shift = p->log_scale_shift;
    if (s_ready) {
        FrontendFreeStateContents(&s_state);
        s_ready = 0;
    }
    if (!FrontendPopulateState(&c, &s_state, p->sample_rate_hz)) {
        return -1;
    }
    s_ready = 1;
    return 0;
}

void ps_fe_reset(void)
{
    if (s_ready) {
        FrontendReset(&s_state);
    }
}

int ps_fe_process(const int16_t *samples, size_t n, size_t *consumed, uint16_t *out)
{
    struct FrontendOutput o = FrontendProcessSamples(&s_state, samples, n, consumed);
    if (o.size == 0) {
        return 0;
    }
    memcpy(out, o.values, o.size * sizeof(uint16_t));
    return 1;
}

size_t ps_fe_process_all(const int16_t *samples, size_t n, uint16_t *out, size_t max_frames)
{
    size_t frames = 0;
    while (n > 0 && frames < max_frames) {
        size_t used = 0;
        frames += (size_t)ps_fe_process(samples, n, &used, out + frames * s_state.filterbank.num_channels);
        samples += used;
        n -= used;
    }
    return frames;
}
