/* PS26172 firmware — M1 build: physical audio path verification + capture link.
 *
 * Boot:  link_init -> @BOOT/@CFG/@MEM
 *        -> stereo probe: MIC_SETTLE, power-up blanking (P-19), per-slot stats, off-slot
 *           behaviour (P-06/P-07), DMA byte rate
 *        -> mono probe (EXP-10): does MONO halve DMA traffic, which mask carries the mic
 *        -> continuous 24-bit mono capture over serial_link (host/capture.py)
 *
 * dBFS convention in all @ lines: RMS values are AES17 (0 dBFS = RMS of a full-scale sine);
 * peak values are sample peak relative to full scale.
 */
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <string.h>

#include "audio_capture.h"
#include "esp_cpu.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "instrument.h"
#include "audio_ring.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include "kws_engine.h"
#include "netstream.h"
#include "ps_frontend.h"
#include "ps_frontend_config.h"
#include "sdkconfig.h"
#include "serial_link.h"

#define LINK_TYPE_FEATURES 3 /* u32 frame_idx, u32 end_sample, u16 bands, bands x u16 */

static const ps_fe_params_t s_fe_params = {
    .sample_rate_hz = PS_FE_SAMPLE_RATE_HZ,
    .window_ms = PS_FE_WINDOW_MS,
    .hop_ms = PS_FE_HOP_MS,
    .mel_bands = PS_FE_MEL_BANDS,
    .mel_low_hz = PS_FE_MEL_LOW_HZ,
    .mel_high_hz = PS_FE_MEL_HIGH_HZ,
    .fb_output_scale_shift = PS_FE_FB_OUTPUT_SCALE_SHIFT,
    .nr_smoothing_bits = PS_FE_NR_SMOOTHING_BITS,
    .nr_even_smoothing = PS_FE_NR_EVEN_SMOOTHING,
    .nr_odd_smoothing = PS_FE_NR_ODD_SMOOTHING,
    .nr_min_signal_remaining = PS_FE_NR_MIN_SIGNAL_REMAINING,
    .pcan_enable = PS_FE_PCAN_ENABLE,
    .pcan_strength = PS_FE_PCAN_STRENGTH,
    .pcan_offset = PS_FE_PCAN_OFFSET,
    .pcan_gain_bits = PS_FE_PCAN_GAIN_BITS,
    .log_enable = PS_FE_LOG_ENABLE,
    .log_scale_shift = PS_FE_LOG_SCALE_SHIFT,
};

#define FS        CONFIG_PS_SAMPLE_RATE_HZ
#define HOP       (FS / 100)  /* 10 ms hop = 160 samples @ 16 kHz (§7.2) */
#define DESC_NUM  4           /* §7.1: 4 x 160-frame DMA descriptors */
#define POOL_N    64          /* audio + feature frame per 10 ms hop: 320 ms of slack */
#define AUDIO_HDR 8           /* u32 first_sample, u8 bytes_per_sample, u8 slot, u16 n */
#define FS24      8388608.0   /* 2^23 */
#define SQRT2     1.4142135623730951

static const ac_config_t s_cfg = {
    .sample_rate_hz = FS,
    .bck_gpio = CONFIG_PS_I2S_BCK_GPIO,
    .ws_gpio = CONFIG_PS_I2S_WS_GPIO,
    .sd_gpio = CONFIG_PS_I2S_SD_GPIO,
    .dma_desc_num = DESC_NUM,
    .dma_frame_num = HOP,
#if CONFIG_PS_I2S_FORMAT_MSB
    .format = AC_FMT_MSB,
#else
    .format = AC_FMT_PHILIPS,
#endif
#if CONFIG_PS_I2S_BCLK_INV
    .bclk_inv = true,
#else
    .bclk_inv = false,
#endif
};

typedef struct {
    uint64_t n;
    double sum;
    double sumsq;
    int32_t peak;
    uint32_t lowbyte_nz; /* words with bits 7:0 set — the INMP441 only drives 24 of 32 bits */
    uint32_t lsb1;       /* samples whose 24-bit LSB is 1: ~50 % when aligned, 0 % if one bit late */
    uint32_t zeros;
    int64_t first_nz_frame;
} slot_stats_t;

static double rms24(const slot_stats_t *s)
{
    return s->n ? sqrt(s->sumsq / (double)s->n) : 0.0;
}

static double dbfs_rms(double rms, double full_scale)
{
    return rms > 0 ? 20.0 * log10(rms * SQRT2 / full_scale) : -999.0;
}

/* Captures discard_ms + measure_ms of audio; stats cover only the measure window, except
 * first_nz_frame, which counts from the I2S clock start. Returns the DMA byte rate. */
static uint32_t probe(const ac_config_t *cfg, i2s_slot_mode_t mode, i2s_std_slot_mask_t mask,
                      uint32_t discard_ms, uint32_t measure_ms, slot_stats_t *st)
{
    static int32_t buf[HOP * 2];
    const int ch = (mode == I2S_SLOT_MODE_STEREO) ? 2 : 1;
    for (int s = 0; s < ch; s++) {
        memset(&st[s], 0, sizeof st[s]);
        st[s].first_nz_frame = -1;
    }
    if (ac_open(cfg, mode, mask) != ESP_OK) {
        return 0;
    }
    const uint64_t discard = (uint64_t)FS * discard_ms / 1000;
    const uint64_t total = discard + (uint64_t)FS * measure_ms / 1000;
    uint64_t frame = 0, bytes = 0;
    const int64_t t0 = esp_timer_get_time();
    while (frame < total) {
        size_t got = 0;
        if (ac_read(buf, HOP * ch * sizeof(int32_t), &got, 1000) != ESP_OK) {
            break;
        }
        bytes += got;
        for (size_t i = 0; i < got / (ch * sizeof(int32_t)); i++, frame++) {
            for (int s = 0; s < ch; s++) {
                const int32_t w = buf[i * ch + s];
                slot_stats_t *p = &st[s];
                if (w != 0 && p->first_nz_frame < 0) {
                    p->first_nz_frame = (int64_t)frame;
                }
                if (frame < discard) {
                    continue;
                }
                const int32_t x = w >> 8;
                const int32_t a = x < 0 ? -x : x;
                p->n++;
                p->sum += x;
                p->sumsq += (double)x * x;
                if (a > p->peak) {
                    p->peak = a;
                }
                if (w & 0xFF) {
                    p->lowbyte_nz++;
                }
                if (x & 1) {
                    p->lsb1++;
                }
                if (w == 0) {
                    p->zeros++;
                }
            }
        }
    }
    const int64_t dt = esp_timer_get_time() - t0;
    ac_close();
    return dt > 0 ? (uint32_t)(bytes * 1000000ULL / (uint64_t)dt) : 0;
}

static double frac(uint32_t k, const slot_stats_t *s)
{
    return s->n ? (double)k / (double)s->n : 0.0;
}

static void report_slot(const char *phase, int slot, const slot_stats_t *s)
{
    link_text("@DIAG phase=%s slot=%d n=%" PRIu64 " dc=%.1f rms24=%.1f rms_dbfs=%.2f peak_dbfs=%.2f "
              "lowbyte_nz_frac=%.4f lsb1_frac=%.4f zero_frac=%.4f first_nz_ms=%.2f\n",
              phase, slot, s->n, s->n ? s->sum / (double)s->n : 0.0, rms24(s), dbfs_rms(rms24(s), FS24),
              s->peak ? 20.0 * log10(s->peak / FS24) : -999.0, frac(s->lowbyte_nz, s), frac(s->lsb1, s),
              frac(s->zeros, s), s->first_nz_frame < 0 ? -1.0 : (double)s->first_nz_frame * 1000.0 / FS);
}

/* Alignment sweep: for each framing x BCK edge, an aligned capture has a random 24-bit LSB in
 * the mic slot (lsb1 ~ 0.5) and nothing in the empty slot. A capture that is k bits late shows
 * lsb1 = 0 and leaks the next sample's sign bits into the empty slot's low byte. */
static void alignment_sweep(void)
{
    static const struct {
        ac_format_t fmt;
        bool inv;
        const char *name;
    } combos[] = {
        {AC_FMT_PHILIPS, false, "PHILIPS"},
        {AC_FMT_MSB, false, "MSB"},
        {AC_FMT_PHILIPS, true, "PHILIPS_INV"},
        {AC_FMT_MSB, true, "MSB_INV"},
    };
    for (size_t i = 0; i < sizeof combos / sizeof combos[0]; i++) {
        ac_config_t c = s_cfg;
        c.format = combos[i].fmt;
        c.bclk_inv = combos[i].inv;
        slot_stats_t st[2];
        probe(&c, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH, 50, 250, st);
        link_text("@ALIGN cfg=%s s0_rms_dbfs=%.2f s0_dc=%.1f s0_lsb1_frac=%.4f s0_lowbyte_nz=%.4f "
                  "s1_rms_dbfs=%.2f s1_lowbyte_nz=%.4f s1_zero_frac=%.4f\n",
                  combos[i].name, dbfs_rms(rms24(&st[0]), FS24), st[0].n ? st[0].sum / (double)st[0].n : 0.0,
                  frac(st[0].lsb1, &st[0]), frac(st[0].lowbyte_nz, &st[0]), dbfs_rms(rms24(&st[1]), FS24),
                  frac(st[1].lowbyte_nz, &st[1]), frac(st[1].zeros, &st[1]));
    }
}

/* ---- continuous capture ------------------------------------------------------------ */

typedef struct {
    uint16_t len;
    uint8_t buf[LINK_HDR_BYTES + AUDIO_HDR + HOP * 3 + LINK_CRC_BYTES];
} txslot_t;

static txslot_t s_pool[POOL_N];
static QueueHandle_t s_free_q;
static QueueHandle_t s_tx_q;
static TaskHandle_t s_reader;
static TaskHandle_t s_tx;
static volatile uint32_t s_samples;
static volatile uint32_t s_pool_drops;
static volatile uint32_t s_short_reads;
static volatile int32_t s_level_db10 = -9990; /* int16-domain RMS of the last second, dBFS x 10 */
static volatile int32_t s_peak16;
/* I-2 per-stage attribution: front-end CPU cycles per 10 ms hop, over the last STATS second. */
static volatile uint32_t s_fe_cyc_mean;
static volatile uint32_t s_fe_cyc_max;
static volatile uint32_t s_fe_frames;

static void enqueue_features(uint32_t frame_idx, uint32_t end_sample, const uint16_t *v)
{
    uint8_t k;
    if (xQueueReceive(s_free_q, &k, 0) != pdTRUE) {
        s_pool_drops++;
        return;
    }
    uint8_t *pl = s_pool[k].buf + LINK_HDR_BYTES;
    memcpy(pl, &frame_idx, 4);
    memcpy(pl + 4, &end_sample, 4);
    const uint16_t bands = PS_FE_MEL_BANDS;
    memcpy(pl + 8, &bands, 2);
    memcpy(pl + 10, v, bands * sizeof(uint16_t));
    s_pool[k].len = (uint16_t)link_build_frame(s_pool[k].buf, LINK_TYPE_FEATURES, pl, 10 + bands * 2);
    xQueueSend(s_tx_q, &k, 0);
}

#if CONFIG_PS_KWS_ENABLE
/* ---- SS-4/SS-5: windowed KWS inference + decision logic (§8.6, DEC-11) ----------------------
 * Schedule, smoothing and refractory mirror model/eval/eval_stream.py exactly, so device posteriors
 * and triggers can be compared one-to-one with the host evaluation. */
#define KWS_WIN 100
#define LINK_TYPE_POSTERIOR 4 /* u32 frame, i8 raw model output, u8 trigger */
static int8_t s_fring[KWS_WIN][PS_FE_MEL_BANDS];
static int8_t s_win[KWS_WIN * PS_FE_MEL_BANDS];
static kws_info_t s_kws;
static volatile uint32_t s_inf_count;
static volatile uint32_t s_inf_cyc_mean;
static volatile uint32_t s_inf_cyc_max;
static volatile uint32_t s_kw_triggers;

static void enqueue_posterior(uint32_t frame, int8_t raw, uint8_t trig)
{
    uint8_t k;
    if (xQueueReceive(s_free_q, &k, 0) != pdTRUE) {
        s_pool_drops++;
        return;
    }
    uint8_t *pl = s_pool[k].buf + LINK_HDR_BYTES;
    memcpy(pl, &frame, 4);
    pl[4] = (uint8_t)raw;
    pl[5] = trig;
    s_pool[k].len = (uint16_t)link_build_frame(s_pool[k].buf, LINK_TYPE_POSTERIOR, pl, 6);
    xQueueSend(s_tx_q, &k, 0);
}

static void kws_on_frame(uint32_t f, const uint16_t *feat)
{
    static float ring_p[CONFIG_PS_KWS_AVG_N]; /* zero-initialised: matches np.convolve(..., "full") start-up */
    static uint32_t n_inf, last_trig_frame, cyc_max;
    static uint64_t cyc_sum;
    static bool any_trig, detect_high;

    if (detect_high) { /* ~10 ms IN-2 pulse: raised at a trigger, lowered on the next frame */
        gpio_set_level(CONFIG_PS_INST_DETECT_GPIO, 0);
        detect_high = false;
    }
    int8_t *row = s_fring[f % KWS_WIN];
    for (int b = 0; b < PS_FE_MEL_BANDS; b++) {
        row[b] = ps_fe_to_int8(feat[b]);
    }
    if (f < KWS_WIN - 1 || (f - (KWS_WIN - 1)) % CONFIG_PS_KWS_STRIDE_FRAMES) {
        return;
    }
    for (int i = 0; i < KWS_WIN; i++) {
        memcpy(s_win + i * PS_FE_MEL_BANDS, s_fring[(f - (KWS_WIN - 1) + i) % KWS_WIN], PS_FE_MEL_BANDS);
    }
    int8_t raw;
    uint32_t cyc;
    const float p = kws_infer(s_win, &raw, &cyc);
    ring_p[n_inf % CONFIG_PS_KWS_AVG_N] = p;
    n_inf++;
    float avg = 0;
    for (int i = 0; i < CONFIG_PS_KWS_AVG_N; i++) {
        avg += ring_p[i];
    }
    avg /= CONFIG_PS_KWS_AVG_N;
    uint8_t trig = 0;
    if (avg >= CONFIG_PS_KWS_THRESHOLD_PCT / 100.0f &&
        (!any_trig || f - last_trig_frame >= CONFIG_PS_KWS_REFRACTORY_MS / PS_FE_HOP_MS)) {
        trig = 1;
        any_trig = true;
        last_trig_frame = f;
        gpio_set_level(CONFIG_PS_INST_DETECT_GPIO, 1);
        detect_high = true;
        s_kw_triggers++;
        int streamed = 0;
#if CONFIG_PS_NET_ENABLE
        const ns_trigger_t nt = {.kw_frame = f, .trig_sample = ring_w(), .t_detect_us = esp_timer_get_time(), .raw = raw};
        streamed = ns_trigger(&nt) ? 1 : 0;
#endif
        link_text("@KW frame=%" PRIu32 " t_ms=%" PRIu32 " p=%.3f avg=%.3f raw=%d streamed=%d\n", f,
                  (uint32_t)((PS_FE_WINDOW_MS) + f * PS_FE_HOP_MS), (double)p, (double)avg, raw, streamed);
    }
    enqueue_posterior(f, raw, trig);
    cyc_sum += cyc;
    cyc_max = cyc > cyc_max ? cyc : cyc_max;
    if (n_inf % 50 == 0) {
        s_inf_cyc_mean = (uint32_t)(cyc_sum / 50);
        s_inf_cyc_max = cyc_max;
        cyc_sum = 0;
        cyc_max = 0;
    }
    s_inf_count = n_inf;
}
#endif

static void reader_task(void *arg)
{
    const i2s_std_slot_mask_t mask = (i2s_std_slot_mask_t)(uintptr_t)arg;
    static int32_t raw[HOP];
    ESP_ERROR_CHECK(ac_open(&s_cfg, I2S_SLOT_MODE_MONO, mask));
    /* The clock was stopped between probes: skip the INMP441 standby recovery (P-20, 16 ms). */
    for (int i = 0; i < 5; i++) {
        size_t got;
        ac_read(raw, sizeof raw, &got, 1000);
    }

    uint32_t idx = 0;
    int64_t acc = 0;
    uint32_t acc_n = 0;
    int32_t pk = 0;
    static int16_t i16[HOP];
    static uint16_t feat[PS_FE_MEL_BANDS];
    uint32_t fe_frames = 0;
    uint64_t fe_cyc_sum = 0;
    uint32_t fe_cyc_max = 0, fe_hops = 0;
    for (;;) {
        size_t got = 0;
        if (ac_read(raw, sizeof raw, &got, 1000) != ESP_OK || got != sizeof raw) {
            s_short_reads++;
            continue;
        }

        /* Front end on the int16 samples the model will see (word >> 16, DEC-09). */
        for (int i = 0; i < HOP; i++) {
            i16[i] = (int16_t)(raw[i] >> 16);
        }
        ring_write(i16, HOP); /* SS-2 unified ring: pre-roll + stream source (§8.4) */
        const uint32_t c0 = esp_cpu_get_cycle_count();
        size_t off = 0;
        int new_frame = 0; /* hop == window step, so at most one feature frame per hop */
        while (off < HOP) {
            size_t used = 0;
            const int produced = ps_fe_process(i16 + off, HOP - off, &used, feat);
            off += used;
            if (produced) {
                enqueue_features(fe_frames++, idx + (uint32_t)off, feat);
                new_frame = 1;
            }
        }
        const uint32_t dc = esp_cpu_get_cycle_count() - c0; /* includes enqueue: an upper bound */
#if CONFIG_PS_KWS_ENABLE
        if (new_frame) {
            kws_on_frame(fe_frames - 1, feat); /* inference timed separately (I-2 attribution) */
        }
#endif
        fe_cyc_sum += dc;
        fe_cyc_max = dc > fe_cyc_max ? dc : fe_cyc_max;
        if (++fe_hops == 100) {
            s_fe_cyc_mean = (uint32_t)(fe_cyc_sum / fe_hops);
            s_fe_cyc_max = fe_cyc_max;
            s_fe_frames = fe_frames;
            fe_cyc_sum = 0;
            fe_cyc_max = 0;
            fe_hops = 0;
        }
        /* Level meter in the int16 domain the model will see: x16 = word >> 16 (§2.4). */
        for (int i = 0; i < HOP; i++) {
            const int32_t x16 = raw[i] >> 16;
            const int32_t a = x16 < 0 ? -x16 : x16;
            acc += (int64_t)x16 * x16;
            if (a > pk) {
                pk = a;
            }
        }
        acc_n += HOP;
        if (acc_n >= FS) {
            const double r = sqrt((double)acc / acc_n);
            s_level_db10 = r > 0 ? (int32_t)lround(200.0 * log10(r * SQRT2 / 32768.0)) : -9990;
            s_peak16 = pk;
            acc = 0;
            acc_n = 0;
            pk = 0;
        }

        uint8_t k;
        if (xQueueReceive(s_free_q, &k, 0) != pdTRUE) {
            s_pool_drops++;
            idx += HOP;
            s_samples = idx;
            continue;
        }
        uint8_t *pl = s_pool[k].buf + LINK_HDR_BYTES;
        pl[0] = (uint8_t)idx;
        pl[1] = (uint8_t)(idx >> 8);
        pl[2] = (uint8_t)(idx >> 16);
        pl[3] = (uint8_t)(idx >> 24);
        pl[4] = 3;
        pl[5] = (mask == I2S_STD_SLOT_RIGHT) ? 1 : 0;
        pl[6] = (uint8_t)(HOP & 0xFF);
        pl[7] = (uint8_t)(HOP >> 8);
        uint8_t *d = pl + AUDIO_HDR;
        for (int i = 0; i < HOP; i++) {
            const int32_t x = raw[i] >> 8; /* full 24-bit sample; host derives int16 as x >> 8 */
            d[0] = (uint8_t)x;
            d[1] = (uint8_t)(x >> 8);
            d[2] = (uint8_t)(x >> 16);
            d += 3;
        }
        s_pool[k].len = (uint16_t)link_build_frame(s_pool[k].buf, LINK_TYPE_AUDIO, pl, AUDIO_HDR + HOP * 3);
        xQueueSend(s_tx_q, &k, 0);
        idx += HOP;
        s_samples = idx;
    }
}

static void tx_task(void *arg)
{
    for (;;) {
        uint8_t k;
        xQueueReceive(s_tx_q, &k, portMAX_DELAY);
        link_write_frame(s_pool[k].buf, s_pool[k].len);
        xQueueSend(s_free_q, &k, 0);
    }
}

void app_main(void)
{
    ESP_ERROR_CHECK(link_init());
    /* Hold the I2S clock off until the host is listening. The INMP441's power-up blanking is
     * counted in SCK cycles (P-19), so waiting here does not change what the probe measures. */
    const int32_t waited_ms = link_wait_host(30000);
    inst_boot_report();
    link_text("@SYNC host_waited_ms=%" PRId32 "\n", waited_ms);
    link_text("@CFG fs=%d hop=%d bck=%d ws=%d sd=%d fmt=%s bclk_inv=%d settle_ms=%d dma_desc=%d dma_frames=%d "
              "slot_bits=32 i16_shift=16\n",
              FS, HOP, CONFIG_PS_I2S_BCK_GPIO, CONFIG_PS_I2S_WS_GPIO, CONFIG_PS_I2S_SD_GPIO,
              s_cfg.format == AC_FMT_MSB ? "MSB" : "PHILIPS", s_cfg.bclk_inv ? 1 : 0, CONFIG_PS_MIC_SETTLE_MS,
              DESC_NUM, HOP);
    inst_mem_report("boot");

    /* Stereo probe first (it sees the first I2S clock after boot, so it also measures blanking). */
    slot_stats_t st[2];
    const uint32_t stereo_bps = probe(&s_cfg, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH, CONFIG_PS_MIC_SETTLE_MS, 1000, st);
    link_text("@DIAG phase=stereo bytes_per_s=%" PRIu32 "\n", stereo_bps);
    report_slot("stereo", 0, &st[0]);
    report_slot("stereo", 1, &st[1]);
    alignment_sweep();
    const int active = rms24(&st[1]) > rms24(&st[0]) ? 1 : 0;
    const double stereo_rms = rms24(&st[active]);
    const bool no_signal = stereo_rms < 16.0; /* mic self-noise alone should be ~hundreds of LSB24 */

    /* Mono probe (EXP-10). Try the mask matching the active stereo slot first. */
    const i2s_std_slot_mask_t masks[2] = {
        active == 0 ? I2S_STD_SLOT_LEFT : I2S_STD_SLOT_RIGHT,
        active == 0 ? I2S_STD_SLOT_RIGHT : I2S_STD_SLOT_LEFT,
    };
    i2s_std_slot_mask_t chosen = masks[0];
    double best = -1.0;
    for (int m = 0; m < 2; m++) {
        slot_stats_t ms;
        const uint32_t bps = probe(&s_cfg, I2S_SLOT_MODE_MONO, masks[m], 50, 500, &ms);
        link_text("@DIAG phase=mono mask=%s bytes_per_s=%" PRIu32 " rms_dbfs=%.2f zero_frac=%.4f\n",
                  masks[m] == I2S_STD_SLOT_LEFT ? "LEFT" : "RIGHT", bps, dbfs_rms(rms24(&ms), FS24),
                  ms.n ? (double)ms.zeros / (double)ms.n : 0.0);
        if (rms24(&ms) > best) {
            best = rms24(&ms);
            chosen = masks[m];
        }
        if (m == 0 && rms24(&ms) >= 0.25 * stereo_rms) {
            break; /* within 12 dB of the stereo slot: mask confirmed */
        }
    }
    link_text("@DIAG decision active_stereo_slot=%d mono_mask=%s no_signal=%d mono_vs_stereo_db=%.2f\n", active,
              chosen == I2S_STD_SLOT_LEFT ? "LEFT" : "RIGHT", no_signal ? 1 : 0,
              (best > 0 && stereo_rms > 0) ? 20.0 * log10(best / stereo_rms) : -999.0);

    link_text("@CFG fe_sha256=%s fe_window_ms=%d fe_hop_ms=%d fe_bands=%d fe_mel_hz=%.0f-%.0f fe_pcan=%d\n",
              PS_FE_JSON_SHA256, PS_FE_WINDOW_MS, PS_FE_HOP_MS, PS_FE_MEL_BANDS, (double)PS_FE_MEL_LOW_HZ,
              (double)PS_FE_MEL_HIGH_HZ, PS_FE_PCAN_ENABLE);
    ESP_ERROR_CHECK(ps_fe_init(&s_fe_params) == 0 ? ESP_OK : ESP_FAIL);
    inst_mem_report("fe_init");
    /* M2 parity fix (DEC-16): replace the libm-computed filterbank weights / PCAN LUT with the host twin's
     * canonical tables, only if they were exported from this exact frontend.json. */
    const int tables_ok = strcmp(ps_fe_tables_fe_sha256, PS_FE_JSON_SHA256) == 0 &&
                          ps_fe_set_tables(ps_fe_tables_weights, ps_fe_tables_unweights, ps_fe_tables_lut,
                                           ps_fe_tables_n_weights, ps_fe_tables_n_lut) == 0;
    link_text("@FETAB canonical_tables_applied=%d\n", tables_ok);
    {
        uint32_t h[PS_FE_N_TABLES];
        ps_fe_table_hashes(h);
        link_text("@FETAB names=" PS_FE_TABLE_NAMES " hashes=%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32
                  ",%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32 ",%08" PRIx32 "\n",
                  h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]);
    }
#if CONFIG_PS_KWS_ENABLE
    gpio_reset_pin(CONFIG_PS_INST_DETECT_GPIO);
    gpio_set_direction(CONFIG_PS_INST_DETECT_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(CONFIG_PS_INST_DETECT_GPIO, 0);
    const esp_err_t kerr = kws_init(&s_kws);
    link_text("@KWS init=%s run=%s model_sha256=%.16s model_bytes=%u arena_bytes=%u arena_used=%u win=%d bands=%d "
              "stride=%d avg_n=%d thr_pct=%d refractory_ms=%d detect_gpio=%d\n",
              esp_err_to_name(kerr), kerr == ESP_OK ? s_kws.run : "-", kerr == ESP_OK ? s_kws.model_sha256 : "-",
              (unsigned)s_kws.model_bytes, (unsigned)s_kws.arena_bytes, (unsigned)s_kws.arena_used_bytes,
              s_kws.win_frames, s_kws.bands, CONFIG_PS_KWS_STRIDE_FRAMES, CONFIG_PS_KWS_AVG_N,
              CONFIG_PS_KWS_THRESHOLD_PCT, CONFIG_PS_KWS_REFRACTORY_MS, CONFIG_PS_INST_DETECT_GPIO);
    ESP_ERROR_CHECK(kerr);
    inst_mem_report("kws_init");
#endif
    ring_init();
#if CONFIG_PS_NET_ENABLE
    link_text("@CFG net=1 server=%s:%d preroll_ms=%d stream_max_ms=%d wifi_ps_none=%d\n", CONFIG_PS_SERVER_HOST,
              CONFIG_PS_SERVER_PORT, CONFIG_PS_PREROLL_MS, CONFIG_PS_STREAM_MAX_MS,
#if CONFIG_PS_WIFI_PS_NONE
              1
#else
              0
#endif
    );
    ESP_ERROR_CHECK(ns_start());
    inst_mem_report("net_start");
#endif

    s_free_q = xQueueCreate(POOL_N, sizeof(uint8_t));
    s_tx_q = xQueueCreate(POOL_N, sizeof(uint8_t));
    for (uint8_t k = 0; k < POOL_N; k++) {
        xQueueSend(s_free_q, &k, 0);
    }
    xTaskCreatePinnedToCore(tx_task, "link_tx", 4096, NULL, 5, &s_tx, 0);
    xTaskCreatePinnedToCore(reader_task, "i2s_reader", 4096, (void *)(uintptr_t)chosen, 20, &s_reader, 1);
    vTaskDelay(pdMS_TO_TICKS(200));
    inst_mem_report("streaming");

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        /* Two lines: one line exceeded LINK_TEXT_MAX (240) and silently lost its tail (run 20260927_145316). */
        const int64_t t_ms = esp_timer_get_time() / 1000;
        link_text("@STATS t_ms=%" PRId64 " samples=%" PRIu32 " pool_drops=%" PRIu32 " link_drops=%" PRIu32
                  " i2s_ovf=%" PRIu32 " short_reads=%" PRIu32 " level_dbfs=%.1f peak16=%" PRId32
                  " heap_free=%u heap_min=%u\n",
                  t_ms, s_samples, s_pool_drops, link_dropped_frames(), ac_overflow_count(), s_short_reads,
                  s_level_db10 / 10.0, s_peak16, (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
        link_text("@PERF t_ms=%" PRId64 " hwm_reader=%u hwm_tx=%u hwm_main=%u fe_frames=%" PRIu32
                  " fe_cyc_mean=%" PRIu32 " fe_cyc_max=%" PRIu32
#if CONFIG_PS_KWS_ENABLE
                  " inf_count=%" PRIu32 " inf_cyc_mean=%" PRIu32 " inf_cyc_max=%" PRIu32 " kw_triggers=%" PRIu32
#endif
                  "\n",
                  t_ms, (unsigned)uxTaskGetStackHighWaterMark(s_reader), (unsigned)uxTaskGetStackHighWaterMark(s_tx),
                  (unsigned)uxTaskGetStackHighWaterMark(NULL), s_fe_frames, s_fe_cyc_mean, s_fe_cyc_max
#if CONFIG_PS_KWS_ENABLE
                  , s_inf_count, s_inf_cyc_mean, s_inf_cyc_max, s_kw_triggers
#endif
                  );
    }
}
