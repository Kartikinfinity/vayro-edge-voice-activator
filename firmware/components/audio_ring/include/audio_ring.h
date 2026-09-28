/* SS-2 · audio_ring — unified int16 ring, one writer (i2s_reader, core 1) and one cross-core
 * reader (streamer, core 0), architecture §8.4. Retention is a property of *not overwriting yet*:
 * the pre-roll is simply w - N samples. Indices are monotonic sample counts (wrap at 2^32).
 * Length = CONFIG_PS_RING_MS (1000 ms = 32 000 B default; product 750 ms = 24 000 B, §8.3 table). */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "sdkconfig.h"

#define RING_SAMPLES (CONFIG_PS_RING_MS * 16)

void ring_init(void);
void ring_write(const int16_t *x, size_t n);  /* writer only */
uint32_t ring_w(void);                         /* current write index (acquire) */

/* Copies n samples starting at monotonic index idx. Returns 0 if idx is no longer in the ring
 * (the reader was lapped: overrun, X9) or not yet written. */
int ring_read(uint32_t idx, int16_t *dst, size_t n);
