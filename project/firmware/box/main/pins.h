/* ESP32-CAM pin plan (spec 3.5). Everything here is to be validated on the bench before boards are ordered. */
#ifndef PINS_H
#define PINS_H

#define PIN_LORA_SCK   14
#define PIN_LORA_MISO  12          /* boot-strap pin (flash voltage): the RA-02 MISO is high-Z while NSS is high, check at reset */
#define PIN_LORA_MOSI  13
#define PIN_LORA_NSS   15          /* boot-strap pin (silences boot log if low) */

#define PIN_I2C_SDA     2
#define PIN_I2C_SCL     4          /* the flash LED on GPIO 4 must be removed */

#define PIN_GPS_RX      3          /* UART0 RX: disconnect while flashing */
#define PIN_GPS_TX      1

/* PCF8574 I/O expander (I2C 0x20). Bit numbers. */
#define PCF_ADDR       0x20
#define PCF_FLAME_DO   0           /* input: KY-026 digital output (active low) */
#define PCF_SUPPLY_OK  1           /* input: power-good from the charger / regulator (low = fault) */
#define PCF_PUMP       2           /* output: relay of the pump */
#define PCF_LORA_RST   3           /* output: RA-02 reset, active low */
#define PCF_CAM_GATE   4           /* output: transistor of the camera supply */
#define PCF_GPS_GATE   5           /* output: transistor of the GPS supply */
#define PCF_GAS_GATE   6           /* output: switch of the BME680 supply (cuts its quiescent current) */
#define PCF_SPARE      7

/* Other I2C devices (ASSUMED parts, not in the spec's pin table: they cost no pin) */
#define I2C_BME680     0x76
#define I2C_MAX17048   0x36        /* battery state of charge */
#define I2C_LM75       0x48        /* housing temperature */

#endif
