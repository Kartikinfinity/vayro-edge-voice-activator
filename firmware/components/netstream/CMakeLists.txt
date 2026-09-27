idf_component_register(SRCS "netstream.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES esp_wifi esp_netif esp_event nvs_flash lwip esp_timer audio_ring serial_link)
