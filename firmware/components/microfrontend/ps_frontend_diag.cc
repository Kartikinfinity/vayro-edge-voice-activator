// Parity diagnostic: FNV-1a hashes of every table the microfrontend computes at init with libm
// (window cosf, filterbank log1pf, PCAN powf, KissFFT cos/sin). Device and host twin print the same
// list; any differing entry is a platform libm rounding difference (M2 parity finding).
#include <cstddef>
#include <cstdint>

#include "ps_frontend.h"
#include "tensorflow/lite/experimental/microfrontend/lib/frontend.h"
#include "tensorflow/lite/experimental/microfrontend/lib/kiss_fft_common.h"
#include "tensorflow/lite/experimental/microfrontend/lib/pcan_gain_control_util.h"

#define FIXED_POINT 16
namespace kissfft_fixed16 {
#include "_kiss_fft_guts.h"
#include "kiss_fft.h"
}  // namespace kissfft_fixed16
#undef FIXED_POINT

namespace {
struct FftrStateMirror {  // layout of struct kiss_fftr_state in kissfft/tools/kiss_fftr.c (no USE_SIMD)
  kissfft_fixed16::kiss_fft_cfg substate;
  kissfft_fixed16::kiss_fft_cpx* tmpbuf;
  kissfft_fixed16::kiss_fft_cpx* super_twiddles;
};

uint32_t fnv1a(const void* p, size_t n, uint32_t h = 2166136261u) {
  const uint8_t* b = static_cast<const uint8_t*>(p);
  for (size_t i = 0; i < n; i++) {
    h = (h ^ b[i]) * 16777619u;
  }
  return h;
}
}  // namespace

// Canonical-table support (M2 parity fix): the filterbank weights (log1pf) and the PCAN gain LUT (powf)
// differ by libm rounding between the device (newlib) and the host twin (glibc). The host's tables are
// canonical (training features were computed with them); they are exported to a generated C file and
// copied into the device state after init.
extern "C" size_t ps_fe_state_table_sizes(const struct FrontendState* s, size_t* n_weights, size_t* n_lut) {
  const FilterbankState& fb = s->filterbank;
  *n_weights = fb.channel_weight_starts[fb.num_channels] + fb.channel_widths[fb.num_channels];
  *n_lut = kWideDynamicFunctionLUTSize;
  return 2;
}

extern "C" void ps_fe_state_copy_tables(struct FrontendState* s, int to_state, int16_t* weights, int16_t* unweights,
                                        int16_t* lut) {
  size_t nw, nl;
  ps_fe_state_table_sizes(s, &nw, &nl);
  FilterbankState& fb = s->filterbank;
  int16_t* lut_state = s->pcan_gain_control.gain_lut;
  for (size_t i = 0; i < nw; i++) {
    if (to_state) {
      fb.weights[i] = weights[i];
      fb.unweights[i] = unweights[i];
    } else {
      weights[i] = fb.weights[i];
      unweights[i] = fb.unweights[i];
    }
  }
  for (size_t i = 0; i < nl; i++) {
    if (to_state) {
      lut_state[i] = lut[i];
    } else {
      lut[i] = lut_state[i];
    }
  }
}

extern "C" size_t ps_fe_state_ptr_tables(const struct FrontendState* s, uint32_t out[PS_FE_N_TABLES]) {
  const FilterbankState& fb = s->filterbank;
  const int n1 = fb.num_channels + 1;
  const int n_weights = fb.channel_weight_starts[fb.num_channels] + fb.channel_widths[fb.num_channels];
  const FftrStateMirror* fr = static_cast<const FftrStateMirror*>(s->fft.scratch);
  const int nfft = fr->substate->nfft;
  out[0] = fnv1a(s->window.coefficients, s->window.size * sizeof(int16_t));
  out[1] = fnv1a(fb.channel_frequency_starts, n1 * sizeof(int16_t));
  out[2] = fnv1a(fb.channel_weight_starts, n1 * sizeof(int16_t));
  out[3] = fnv1a(fb.channel_widths, n1 * sizeof(int16_t));
  out[4] = fnv1a(fb.unweights, n_weights * sizeof(int16_t), fnv1a(fb.weights, n_weights * sizeof(int16_t)));
  // PCAN LUT: hash only the entries WideDynamicFunction() reads (0, 1, and 3 per interval 2..32).
  // The index 4*i-3 slots are allocated but never initialised (malloc), so hashing them compared garbage.
  {
    const int16_t* lut = s->pcan_gain_control.gain_lut;
    uint32_t h = fnv1a(lut, 2 * sizeof(int16_t));
    for (int i = 2; i <= kWideDynamicFunctionBits; i++) {
      h = fnv1a(lut + 4 * i - 6, 3 * sizeof(int16_t), h);
    }
    out[5] = h;
  }
  out[6] = fnv1a(fr->substate->twiddles, nfft * sizeof(kissfft_fixed16::kiss_fft_cpx));
  out[7] = fnv1a(fr->super_twiddles, (nfft / 2) * sizeof(kissfft_fixed16::kiss_fft_cpx));
  return PS_FE_N_TABLES;
}
