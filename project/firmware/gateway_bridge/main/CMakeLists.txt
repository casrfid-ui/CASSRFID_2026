set(CORE ${CMAKE_CURRENT_LIST_DIR}/../core)
idf_component_register(
    SRCS main.c ${CORE}/src/bridge_core.c ${CORE}/src/hdlc.c ${CORE}/src/sim800.c
    INCLUDE_DIRS . ${CORE}/include
    REQUIRES ffp sx127x driver esp_timer nvs_flash)
