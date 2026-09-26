#include "audio_capture.h"

#include "esp_attr.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"

static const char *TAG = "audio_capture";

static i2s_chan_handle_t s_rx;
static volatile uint32_t s_ovf;

static bool IRAM_ATTR on_recv_q_ovf(i2s_chan_handle_t h, i2s_event_data_t *e, void *ctx)
{
    s_ovf++;
    return false;
}

esp_err_t ac_open(const ac_config_t *cfg, i2s_slot_mode_t mode, i2s_std_slot_mask_t mask)
{
    esp_err_t ret = ESP_OK;
    i2s_chan_config_t cc = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    cc.dma_desc_num = cfg->dma_desc_num;
    cc.dma_frame_num = cfg->dma_frame_num;
    ESP_RETURN_ON_ERROR(i2s_new_channel(&cc, NULL, &s_rx), TAG, "i2s_new_channel");

    const i2s_std_slot_config_t philips = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, mode);
    const i2s_std_slot_config_t msb = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, mode);
    i2s_std_config_t sc = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(cfg->sample_rate_hz),
        .slot_cfg = (cfg->format == AC_FMT_MSB) ? msb : philips,
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)cfg->bck_gpio,
            .ws = (gpio_num_t)cfg->ws_gpio,
            .dout = I2S_GPIO_UNUSED,
            .din = (gpio_num_t)cfg->sd_gpio,
            .invert_flags = {.mclk_inv = false, .bclk_inv = cfg->bclk_inv, .ws_inv = false},
        },
    };
    sc.slot_cfg.slot_mask = mask;
    ESP_GOTO_ON_ERROR(i2s_channel_init_std_mode(s_rx, &sc), fail, TAG, "init_std_mode");

    i2s_event_callbacks_t cbs = {.on_recv_q_ovf = on_recv_q_ovf};
    ESP_GOTO_ON_ERROR(i2s_channel_register_event_callback(s_rx, &cbs, NULL), fail, TAG, "register_cb");
    ESP_GOTO_ON_ERROR(i2s_channel_enable(s_rx), fail, TAG, "enable");
    return ESP_OK;

fail:
    i2s_del_channel(s_rx);
    s_rx = NULL;
    return ret;
}

void ac_close(void)
{
    if (s_rx) {
        i2s_channel_disable(s_rx);
        i2s_del_channel(s_rx);
        s_rx = NULL;
    }
}

esp_err_t ac_read(int32_t *dst, size_t bytes, size_t *bytes_read, uint32_t timeout_ms)
{
    return i2s_channel_read(s_rx, dst, bytes, bytes_read, timeout_ms);
}

uint32_t ac_overflow_count(void)
{
    return s_ovf;
}
