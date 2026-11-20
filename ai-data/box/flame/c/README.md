# Flame sensor processing, C port (ESP32)

Portable C99, no heap, no I/O, no global state. Checked against `../python`.

```c
#include "flame.h"

uint8_t raw[8];                          // 8 digital reads of the KY-026 DO pin, taken by the firmware
read_flame_pin(raw, 8);
fl_result_t r;
if (fl_process(raw, 8, NULL, &r) == 0) {  // NULL = default config (active low, 5 of 8 vote, no flicker rule)
    // r.detected, r.ratio, r.transitions, r.n
}
```

`fl_process` returns -1 (result untouched) for NULL pointers or a burst length outside 1..`FL_MAX_SAMPLES` (32).
In the box the runtime calls it (`../../runtime`), so the application only fills `box_tick_t.flame_raw`.

## Tests
```
make test        # 43 checks: polarity, vote limits, flicker count, bad arguments
make cli         # host tool used by ../python/tests/test_c_parity.py (5000 random bursts, both polarities)
```
