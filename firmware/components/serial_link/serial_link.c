#include "serial_link.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "sdkconfig.h"

#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#elif CONFIG_ESP_CONSOLE_UART
#include "driver/uart.h"
#include "driver/uart_vfs.h"
#else
#error "serial_link needs the console on UART or USB-Serial-JTAG"
#endif

#define TX_RING_BYTES 16384

static const uint8_t SYNC[4] = {0xA5, 0x5A, 0x26, 0x17};
static SemaphoreHandle_t s_mtx;
static volatile uint32_t s_dropped;

static uint16_t crc16_ccitt(const uint8_t *p, size_t n)
{
    uint16_t c = 0xFFFF;
    while (n--) {
        c ^= (uint16_t)(*p++) << 8;
        for (int i = 0; i < 8; i++) {
            c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
        }
    }
    return c;
}

size_t link_build_frame(uint8_t *out, uint8_t type, const void *payload, uint16_t len)
{
    memcpy(out, SYNC, sizeof SYNC);
    out[4] = type;
    out[5] = 0;
    out[6] = (uint8_t)(len & 0xFF);
    out[7] = (uint8_t)(len >> 8);
    if (len && payload != out + LINK_HDR_BYTES) {
        memcpy(out + LINK_HDR_BYTES, payload, len);
    }
    uint16_t crc = crc16_ccitt(out + 4, 4u + len);
    out[LINK_HDR_BYTES + len] = (uint8_t)(crc & 0xFF);
    out[LINK_HDR_BYTES + len + 1] = (uint8_t)(crc >> 8);
    return LINK_HDR_BYTES + len + LINK_CRC_BYTES;
}

static esp_err_t raw_write(const uint8_t *p, size_t n)
{
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    if (!usb_serial_jtag_is_connected()) {
        return ESP_FAIL;
    }
    size_t off = 0;
    while (off < n) {
        int w = usb_serial_jtag_write_bytes(p + off, n - off, pdMS_TO_TICKS(100));
        if (w <= 0) {
            return ESP_FAIL;
        }
        off += (size_t)w;
    }
    return ESP_OK;
#else
    int w = uart_write_bytes(CONFIG_ESP_CONSOLE_UART_NUM, p, n);
    return (w == (int)n) ? ESP_OK : ESP_FAIL;
#endif
}

esp_err_t link_write_frame(const uint8_t *frame, size_t n)
{
    xSemaphoreTake(s_mtx, portMAX_DELAY);
    esp_err_t r = raw_write(frame, n);
    xSemaphoreGive(s_mtx);
    if (r != ESP_OK) {
        s_dropped++;
    }
    return r;
}

static void text_frame(const char *fmt, va_list ap)
{
    uint8_t f[LINK_HDR_BYTES + LINK_TEXT_MAX + LINK_CRC_BYTES];
    int n = vsnprintf((char *)f + LINK_HDR_BYTES, LINK_TEXT_MAX, fmt, ap);
    if (n <= 0) {
        return;
    }
    if (n >= LINK_TEXT_MAX) {
        n = LINK_TEXT_MAX - 1;
    }
    size_t tot = link_build_frame(f, LINK_TYPE_TEXT, f + LINK_HDR_BYTES, (uint16_t)n);
    link_write_frame(f, tot);
}

void link_text(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    text_frame(fmt, ap);
    va_end(ap);
}

static int log_to_link(const char *fmt, va_list ap)
{
    text_frame(fmt, ap);
    return 0;
}

esp_err_t link_init(void)
{
    s_mtx = xSemaphoreCreateMutex();
    if (!s_mtx) {
        return ESP_ERR_NO_MEM;
    }
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    usb_serial_jtag_driver_config_t cfg = {
        .tx_buffer_size = TX_RING_BYTES,
        .rx_buffer_size = 256,
    };
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&cfg));
    usb_serial_jtag_vfs_use_driver();
#else
    ESP_ERROR_CHECK(uart_driver_install(CONFIG_ESP_CONSOLE_UART_NUM, 256, TX_RING_BYTES, 0, NULL, 0));
    uart_vfs_dev_use_driver(CONFIG_ESP_CONSOLE_UART_NUM);
#endif
    esp_log_set_vprintf(log_to_link);
    return ESP_OK;
}

uint32_t link_dropped_frames(void)
{
    return s_dropped;
}
