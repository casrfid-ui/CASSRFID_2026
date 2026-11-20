# ESP-IDF project of the gateway bridge (ESP32 DevKit + RA-02 + SIM800L, powering the SBC). NOT built in this repository.
cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS ${CMAKE_CURRENT_LIST_DIR}/../box/components/ffp ${CMAKE_CURRENT_LIST_DIR}/../common/sx127x)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(forest_gateway_bridge)
