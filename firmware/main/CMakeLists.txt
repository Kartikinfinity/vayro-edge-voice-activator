idf_component_register(SRCS "app_main.c"
                       INCLUDE_DIRS "."
                       REQUIRES audio_capture serial_link instrument microfrontend kws_engine
                                esp_timer heap esp_hw_support esp_driver_gpio)
