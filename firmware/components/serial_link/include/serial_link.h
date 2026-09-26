/* SS-debug · serial_link — framed, CRC-checked device→host link over the console port.
 *
 * Used for M1 audio verification and for recording training / held-out data through
 * the physical INMP441. It is NOT the product streaming path (that is TCP, SS-6, M5).
 *
 * Frame: sync A5 5A 26 17 | type u8 | flags u8 | len u16 LE | payload[len] | crc16 LE
 * CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over type..payload.
 * All ESP_LOG output is routed into TEXT frames once link_init() has run, so binary
 * audio and log text never interleave inside a frame.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#define LINK_TYPE_AUDIO   1
#define LINK_TYPE_TEXT    2
#define LINK_HDR_BYTES    8
#define LINK_CRC_BYTES    2
#define LINK_MAX_PAYLOAD  1024
#define LINK_TEXT_MAX     240

esp_err_t link_init(void);

/* Writes header + CRC around a payload that may already sit at out + LINK_HDR_BYTES.
 * Returns the total frame length. */
size_t link_build_frame(uint8_t *out, uint8_t type, const void *payload, uint16_t len);

/* Thread-safe; returns ESP_FAIL (and counts a drop) if the host side is not draining. */
esp_err_t link_write_frame(const uint8_t *frame, size_t n);

void link_text(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

uint32_t link_dropped_frames(void);
