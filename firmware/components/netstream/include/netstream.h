/* SS-6 streamer + SS-7 netlink (architecture §8-§10).
 *
 * Wi-Fi STA + ONE warm TCP connection opened at boot (§9.2), kept alive by clock pings every 10 s
 * (NTP-style 4-timestamp exchange, IN-6). On a keyword trigger, audio is streamed from the unified
 * ring starting PREROLL_MS before the trigger (§8.3), as 20 ms PCM16 frames, 2 frames per packet,
 * each packet with the 8-byte §9.3 header. The server ends the stream (endpointing); a device-side
 * hard timeout and an OVERRUN marker (ring lapped, X9) are the fallbacks.
 *
 * Wire format (little-endian). Header: u8 magic 0xA7 | u8 flags | u8 codec | u16 seq | u24 t_device_ms.
 * The §9.3 header has no length field, so payload sizes are fixed per packet type:
 *   device->server  START 0x01: 32 B  {u32 activation, u32 kw_frame, u64 t_detect_us, u32 preroll_ms,
 *                                     u32 first_sample, i8 raw_posterior, u8 pad[3], u32 reserved}
 *                   CONT  0x02: 1280 B PCM16 (640 samples = 2 x 20 ms)
 *                   END   0x04: 16 B  {u32 activation, u32 samples_sent, u32 min_slack_samples, u32 reason}
 *                   OVERRUN 0x08: 0 B (followed by END)
 *                   PING  0x20: 8 B   {u64 t1_us}
 *                   INFO  0x40: 16 B  {i64 clock_offset_us, u32 rtt_us, u32 pings}
 *   server->device  PONG  0x80: 24 B  {u64 t1_us, u64 t2_us, u64 t3_us}   (server clock, µs)
 *                   END   0x04: 4 B   {u32 activation}                     (server endpointing)
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    uint32_t kw_frame;
    uint32_t trig_sample; /* ring write index at the trigger */
    int64_t t_detect_us;  /* esp_timer at the trigger (IN-4) */
    int8_t raw;
} ns_trigger_t;

esp_err_t ns_start(void);                   /* Wi-Fi + net task + streamer task, all on core 0 */
bool ns_trigger(const ns_trigger_t *t);     /* non-blocking; false if busy or not connected */
bool ns_connected(void);
