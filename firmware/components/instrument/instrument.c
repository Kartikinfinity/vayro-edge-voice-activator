#include "instrument.h"

#include <inttypes.h>

#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_idf_version.h"
#include "esp_system.h"
#include "sdkconfig.h"
#include "serial_link.h"

static const char *reset_reason_str(esp_reset_reason_t r)
{
    switch (r) {
    case ESP_RST_POWERON: return "POWERON";
    case ESP_RST_EXT: return "EXT";
    case ESP_RST_SW: return "SW";
    case ESP_RST_PANIC: return "PANIC";
    case ESP_RST_INT_WDT: return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT: return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_USB: return "USB";
    default: return "OTHER";
    }
}

void inst_mem_report(const char *tag)
{
    const uint32_t caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    link_text("@MEM tag=%s int_total=%u int_free=%u int_min_free=%u int_largest=%u dma_free=%u psram=%s\n",
              tag,
              (unsigned)heap_caps_get_total_size(caps),
              (unsigned)heap_caps_get_free_size(caps),
              (unsigned)heap_caps_get_minimum_free_size(caps),
              (unsigned)heap_caps_get_largest_free_block(caps),
              (unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),
#if CONFIG_SPIRAM
              "ENABLED"
#else
              "disabled_in_sdkconfig"
#endif
    );
}

void inst_boot_report(void)
{
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    uint32_t flash_bytes = 0;
    esp_flash_get_size(NULL, &flash_bytes);
    char elf_sha[17] = {0};
    esp_app_get_elf_sha256(elf_sha, sizeof elf_sha);

    link_text("@BOOT idf=%s elf_sha=%s built=%s_%s cores=%d rev=%d.%d emb_psram=%d flash_bytes=%" PRIu32
              " cpu_mhz=%d reset=%s\n",
              esp_get_idf_version(), elf_sha, esp_app_get_description()->date,
              esp_app_get_description()->time, chip.cores, chip.revision / 100, chip.revision % 100,
              (chip.features & CHIP_FEATURE_EMB_PSRAM) ? 1 : 0, flash_bytes,
              CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ, reset_reason_str(esp_reset_reason()));
}
