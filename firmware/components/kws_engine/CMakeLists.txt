idf_component_register(SRCS "kws_engine.cc" "model_data.c"
                       INCLUDE_DIRS "include"
                       PRIV_INCLUDE_DIRS "."
                       PRIV_REQUIRES espressif__esp-tflite-micro microfrontend esp_hw_support)
