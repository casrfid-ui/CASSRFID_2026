set(CORE ${CMAKE_CURRENT_LIST_DIR}/../core)
idf_component_register(
    SRCS main.c hal_esp32.c i2c_bus.c bme680_drv.c i2c_misc.c cam_esp32.c gps_uart.c
         ${CMAKE_CURRENT_LIST_DIR}/../../../../ai-data/box/runtime/c/esp32/box_nvs.c
         ${CORE}/src/box_app.c ${CORE}/src/box_link.c ${CORE}/src/box_wxsim.c ${CORE}/src/nmea.c
    INCLUDE_DIRS . ${CORE}/include ${CMAKE_CURRENT_LIST_DIR}/../../../../ai-data/box/runtime/c/esp32
    REQUIRES ai_box_blocks ffp sx127x nvs_flash driver esp_timer esp_wifi esp_http_client esp_netif esp_event esp_hw_support esp_system
    PRIV_REQUIRES esp32-camera bme68x)
