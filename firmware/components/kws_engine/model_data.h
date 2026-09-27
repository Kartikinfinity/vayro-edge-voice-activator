#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

extern const char g_kws_model_run[];
extern const char g_kws_model_sha256[];
extern const char g_kws_model_fe_sha256[];
extern const unsigned int g_kws_model_len;
extern const int8_t g_kws_input_lut[256]; /* front-end int8 feature -> model input int8 (host-generated) */
extern const unsigned char g_kws_model[];

#ifdef __cplusplus
}
#endif
