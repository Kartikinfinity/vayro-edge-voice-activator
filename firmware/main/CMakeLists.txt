idf_component_register(SRCS "app_main.c"
                       INCLUDE_DIRS "."
                       REQUIRES audio_capture serial_link instrument microfrontend esp_timer heap esp_hw_support)
