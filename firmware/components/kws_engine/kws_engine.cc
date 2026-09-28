#include "kws_engine.h"

#include <cstring>
#include <new>

#include "esp_cpu.h"
#include "model_data.h"
#include "ps_frontend_config.h"
#include "sdkconfig.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {
constexpr size_t kArenaBytes = CONFIG_PS_KWS_ARENA_BYTES;
alignas(16) uint8_t g_arena[kArenaBytes];
tflite::MicroMutableOpResolver<6> g_resolver;
alignas(tflite::MicroInterpreter) uint8_t g_interp_mem[sizeof(tflite::MicroInterpreter)];
tflite::MicroInterpreter *g_interp = nullptr;
}  // namespace

extern "C" esp_err_t kws_init(kws_info_t *info)
{
    if (std::strcmp(g_kws_model_fe_sha256, PS_FE_JSON_SHA256) != 0) {
        return ESP_ERR_INVALID_VERSION; /* model trained under a different front end (§7.3) */
    }
    const tflite::Model *model = tflite::GetModel(g_kws_model);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        return ESP_ERR_INVALID_VERSION;
    }
    g_resolver.AddConv2D();
    g_resolver.AddDepthwiseConv2D();
    g_resolver.AddReshape();
    g_resolver.AddFullyConnected();
    g_resolver.AddLogistic();
    g_interp = new (g_interp_mem) tflite::MicroInterpreter(model, g_resolver, g_arena, kArenaBytes);
    if (g_interp->AllocateTensors() != kTfLiteOk) {
        return ESP_ERR_NO_MEM;
    }
    const TfLiteTensor *in = g_interp->input(0);
    info->run = g_kws_model_run;
    info->model_sha256 = g_kws_model_sha256;
    info->model_bytes = g_kws_model_len;
    info->arena_bytes = kArenaBytes;
    info->arena_used_bytes = g_interp->arena_used_bytes();
    info->win_frames = in->dims->data[1];
    info->bands = in->dims->data[3];
    return ESP_OK;
}

extern "C" void kws_set_row(int row, const int8_t *features)
{
    TfLiteTensor *in = g_interp->input(0);
    const int bands = in->dims->data[3];
    int8_t *dst = in->data.int8 + row * bands;
    for (int b = 0; b < bands; b++) {
        dst[b] = g_kws_input_lut[(int)features[b] + 128];
    }
}

extern "C" float kws_infer(const int8_t *window, int8_t *raw, uint32_t *cycles)
{
    TfLiteTensor *in = g_interp->input(0);
    int8_t *dst = in->data.int8;
    for (size_t i = 0; i < in->bytes; i++) {
        dst[i] = g_kws_input_lut[(int)window[i] + 128];
    }
    return kws_invoke(raw, cycles);
}

extern "C" float kws_invoke(int8_t *raw, uint32_t *cycles)
{
    const uint32_t c0 = esp_cpu_get_cycle_count();
    g_interp->Invoke();
    *cycles = esp_cpu_get_cycle_count() - c0;
    const TfLiteTensor *out = g_interp->output(0);
    *raw = out->data.int8[0];
    return (out->data.int8[0] - out->params.zero_point) * out->params.scale;
}
