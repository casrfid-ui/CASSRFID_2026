# State machine, C port (ESP32)

Portable C99, no heap, no I/O, no clock: the caller gives the time since the previous wake-up. Checked against `../python`.

```c
#include "state_machine.h"

sm_machine_t sm;
sm_init(&sm, NULL);                      // NULL = default config (same as python Config)

sm_inputs_t x;
sm_inputs_default(&x);                   // eco, dt 30 s, everything else false
x.gas_smoke = (gas.cls == GC_SMOKE);
x.flame = flame_pin;
x.dt_s = seconds_since_previous_step;
sm_output_t o;
sm_step(&sm, &x, &o);                    // o.state, o.interval_s, o.camera_on, o.gps_on, o.actuator,
                                         // o.reasons, o.frames[0..n_frames-1], o.last_gasp
sm_reset(&sm);                           // operator or gateway acknowledgement: leave Fire
```

## Tests
```
make test        # 574 checks: the cases of the Python tests, flame recheck, bad arguments, frame overflow
make cli         # host tool used by ../python/tests/test_c_parity.py
```
