# FWI engine, C port (ESP32)

Portable C99, no heap, no OS call. Checked against the Python reference in `../python`.

## Use on the box
```c
#include "fwi.h"
#include "fwi_nvs.h"                         // flash storage (ESP-IDF)

static fwi_engine_t fwi;

void app_start(void) {
    nvs_flash_init();
    fwi_start_t how = fwi_engine_init(&fwi, &fwi_nvs_storage, NULL, NULL);
    // FWI_START_DEFAULTS on the very first boot, FWI_START_RESTORED after a reboot
}

void every_hour(void) {                      // called once per hour from the RTC
    fwi_input_t in = { .hour = hour_local, .month = month_local,
                       .temp_c = bme_temp, .rh_pct = bme_rh,
                       .wind_kmh = sim_wind, .rain_mm = sim_rain_last_hour };
    fwi_output_t out;
    if (fwi_engine_update_hour(&fwi, &in, &out) == FWI_OK) {
        set_scan_interval(out.mode == FWI_MODE_ALERT ? 30 : 300);
        // out.provisional == 1: the 24 h history still contains default values
    }
}
```

## What the code does
| Need | How |
|---|---|
| Sensor values, time | passed in `fwi_input_t` (BME680, RTC, simulated wind and rain) |
| 24 h rain history | ring buffer inside `fwi_state_t`, one value per hour |
| Saved on the card | the three codes and the 24 h history are written to flash every hour (228-byte blob, CRC32) and read back at boot |
| First 24 h | defaults: FFMC 85, DMC 6, DC 15, rain 0 mm per hour. `provisional` stays 1 until 24 real hours are recorded |
| Bad data | an out-of-range or NaN reading is refused (`FWI_ERR_INPUT`) and the state is not changed |
| Damaged flash | wrong size, magic, version, CRC or content: defaults are used |

## Choices to confirm
- Default rain 0 mm assumes a dry past: danger is not underestimated, but it is overestimated after a rain.
- A reboot is not detected as a time gap. If the box was off for hours, those hours are simply missing from the history.
- The flash is written every hour (8760 writes per year); NVS wear levelling covers this.
- Doubles are emulated in software on the original ESP32. At one call per hour this is irrelevant.

## Tests
```
make test        # 203 checks on defaults, 24 h window, persistence, corruption, bad input
make cli         # host tool used by ../python/tests/test_c_parity.py
```
`esp32/fwi_nvs.c` (ESP-IDF) is a thin adapter over `nvs_get_blob` / `nvs_set_blob`.
