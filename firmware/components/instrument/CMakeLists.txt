idf_component_register(SRCS "instrument.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES serial_link heap esp_app_format esp_hw_support spi_flash esp_system)
