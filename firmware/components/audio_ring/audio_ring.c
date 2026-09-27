#include "audio_ring.h"

#include <stdatomic.h>
#include <string.h>

static int16_t s_buf[RING_SAMPLES];
static _Atomic uint32_t s_w;

void ring_init(void)
{
    memset(s_buf, 0, sizeof s_buf);
    atomic_store(&s_w, 0);
}

void ring_write(const int16_t *x, size_t n)
{
    uint32_t w = atomic_load_explicit(&s_w, memory_order_relaxed);
    for (size_t i = 0; i < n; i++) {
        s_buf[(w + i) % RING_SAMPLES] = x[i];
    }
    atomic_store_explicit(&s_w, w + (uint32_t)n, memory_order_release); /* publish after the data */
}

uint32_t ring_w(void)
{
    return atomic_load_explicit(&s_w, memory_order_acquire);
}

int ring_read(uint32_t idx, int16_t *dst, size_t n)
{
    const uint32_t w = ring_w();
    if ((int32_t)(w - (idx + (uint32_t)n)) < 0) {
        return 0; /* not written yet */
    }
    if ((uint32_t)(w - idx) > RING_SAMPLES) {
        return 0; /* already overwritten: lapped */
    }
    for (size_t i = 0; i < n; i++) {
        dst[i] = s_buf[(idx + i) % RING_SAMPLES];
    }
    /* Re-check: the writer may have lapped us while copying. */
    return (uint32_t)(ring_w() - idx) <= RING_SAMPLES ? 1 : 0;
}
