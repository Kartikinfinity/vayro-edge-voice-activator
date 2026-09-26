/* SS-1 · audio_capture — INMP441 on I2S0, standard mode, 32-bit slots (P-02/P-03).
 *
 * The INMP441 requires exactly 64 SCK per WS frame, so slots are always 32-bit; the
 * 24-bit sample occupies bits 31:8 of each word. BCK = 64 * fs = 1.024 MHz at 16 kHz.
 * The RX framing (Philips vs MSB-justified) and BCK edge are selectable because the
 * alignment that actually captures bit-exact data on this board is decided by measurement
 * (docs/experiments/M1_audio_path.md), not assumed.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "driver/i2s_std.h"
#include "esp_err.h"

typedef enum {
    AC_FMT_PHILIPS = 0, /* MSB one BCK after the WS edge */
    AC_FMT_MSB = 1,     /* MSB on the WS edge */
} ac_format_t;

typedef struct {
    uint32_t sample_rate_hz;
    int bck_gpio;
    int ws_gpio;
    int sd_gpio;
    uint32_t dma_desc_num;
    uint32_t dma_frame_num;
    ac_format_t format;
    bool bclk_inv;
} ac_config_t;

esp_err_t ac_open(const ac_config_t *cfg, i2s_slot_mode_t mode, i2s_std_slot_mask_t mask);
void ac_close(void);
esp_err_t ac_read(int32_t *dst, size_t bytes, size_t *bytes_read, uint32_t timeout_ms);

/* Count of I2S driver receive-queue overflows (DMA data lost because it was not read in time). */
uint32_t ac_overflow_count(void);
