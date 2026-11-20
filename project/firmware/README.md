# firmware
- [box/](box/) ESP32-CAM application. `core/` portable C (host-tested), `main/` + `components/` ESP-IDF layer.
- [gateway_bridge/](gateway_bridge/) gateway ESP32. Same split.
- [common/sx127x/](common/sx127x/) RA-02 driver shared by both.
The `ai-data` C blocks are compiled in place (`components/ai_box_blocks/CMakeLists.txt`), so a fix in `ai-data` reaches the firmware.

## Host tests (PC)
`make -C project/firmware/box/host test` · `make -C project/firmware/box/host sim` · `make -C project/firmware/gateway_bridge/host test`
`box_sim SCENARIO BOX_ID [WAKES] [noack]` prints `unix box hex32` lines (scenarios `quiet smoke fire fault`).

## On the boards (ESP-IDF 5.x)
`idf.py set-target esp32 && idf.py menuconfig && idf.py build flash monitor` inside `box/` or `gateway_bridge/`.
Box options (Kconfig "Box configuration"): box id, other box id, UTC offset, static position, LoRa frequency and power, Wi-Fi, gateway URL, simulation seed.

## Pins
Box: `box/main/pins.h` (LoRa SPI 14/12/13/15, I2C 2/4, GPS 3/1, PCF8574 bits 0-6). Bridge: LoRa SCK18 MISO19 MOSI23 NSS5 RST22, SBC UART1 tx17 rx16, SBC power 4, SIM800 UART2 tx25 rx26, PWRKEY 27.
