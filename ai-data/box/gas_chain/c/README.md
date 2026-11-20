# Gas chain, C port (ESP32)

Portable C99, no heap, no OS call, no global state. Checked against the Python reference in `../python`.

## Use
```c
#include "gas_chain.h"

static gc_chain_t chain;                       // about 1.3 kB, one per sensor

gc_init(&chain, NULL);                         // NULL = default tuning (same as python Config)
// optional, after a reboot: no burn-in and no warm-up
gc_restore(&chain, baseline_from_flash);

double gas[GC_NSTEP], temp[GC_NSTEP], rh[GC_NSTEP];   // one forced measurement per heater step
gc_result_t r;
if (gc_update(&chain, gas, temp, rh, seconds_since_previous_scan, &r) == 0) {
    // r.score 0..1, r.cls (GC_NORMAL / GC_SMOKE / GC_FAULT), r.faults, r.warmup, r.bands[3]
}
double base[GC_NSTEP];
if (gc_snapshot(&chain, base)) { /* save base[] in flash now and then */ }
```

## Files
One file per stage, same names as `stages.py`: `gc_quality.c`, `gc_compensate.c`, `gc_filter.c`, `gc_baseline.c`, `gc_score.c`, `gc_class.c`; the orchestrator is `gc_chain.c`; tuning in `gc_config.c`. Stage functions are declared in `src/gc_internal.h` (used by the unit tests).

## Behaviour to know
- A reading outside the range, or NaN/infinity, makes the scan bad: it never enters the state; three in a row give the fault class.
- `gc_update` returns -1 for NULL pointers or `dt_s <= 0` and changes nothing.
- `median_window` is limited to `GC_MEDIAN_MAX` (9) by the fixed buffers; `gc_config_check` refuses larger values.
- Doubles are emulated in software on the original ESP32 (a few microseconds per operation): the chain runs once per 30 to 300 s, so the cost is negligible; the benefit is C results equal to Python to 1e-9.

## Tests
```
make test        # 2060 checks: every stage alone, then the chain (faults, restore, bad arguments)
make cli         # host tool used by ../python/tests/test_c_parity.py
```
