# ESP-IDF component (firmware build). Host build and tests: `make test` (see Makefile).
idf_component_register(
    SRCS "src/fwi.c" "esp32/fwi_nvs.c"
    INCLUDE_DIRS "include" "esp32"
    REQUIRES nvs_flash)
