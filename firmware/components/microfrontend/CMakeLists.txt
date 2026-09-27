# Vendored TFLM microfrontend (Apache-2.0) + KissFFT (BSD-3). Provenance: PROVENANCE.md.
set(lib tensorflow/lite/experimental/microfrontend/lib)
idf_component_register(
    SRCS "ps_frontend.c"
         "${lib}/fft.cc" "${lib}/fft_util.cc" "${lib}/kiss_fft_int16.cc"
         "${lib}/filterbank.c" "${lib}/filterbank_util.c"
         "${lib}/frontend.c" "${lib}/frontend_util.c"
         "${lib}/log_lut.c" "${lib}/log_scale.c" "${lib}/log_scale_util.c"
         "${lib}/noise_reduction.c" "${lib}/noise_reduction_util.c"
         "${lib}/pcan_gain_control.c" "${lib}/pcan_gain_control_util.c"
         "${lib}/window.c" "${lib}/window_util.c"
    INCLUDE_DIRS "include" "."
    PRIV_INCLUDE_DIRS "kissfft")
# kiss_fft.c / kiss_fftr.c are #included by kiss_fft_int16.cc inside namespace kissfft_fixed16,
# so they are deliberately NOT listed in SRCS.
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-unused-variable -Wno-sign-compare -Wno-maybe-uninitialized)
