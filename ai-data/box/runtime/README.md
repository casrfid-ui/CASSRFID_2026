# Box runtime

Chains FWI → gas chain → state machine in one call per wake-up and keeps the flash copies (FWI state, gas baseline, Fire latch). See `FICHE.md`.

```
make -C c test        # 400 checks: hourly FWI, local time, rain, gas, flame burst, Fire, reboots, flash failures
cd python && pytest   # parity: C runtime vs Python chain of the three blocks, real data at 27 s and at 300 s
```

Layout: `c/include/box_runtime.h` (API), `c/src/box_runtime.c`, `c/esp32/` (NVS adapter, `main.c` skeleton, `board.h`), `python/` (reference).
