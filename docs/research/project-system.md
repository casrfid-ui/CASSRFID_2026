# Project system (firmware + gateway app) — RES-SYS-n

## RES-SYS-1 — Frame protocol, C and Python agree
**Question** Does one 16-byte layout survive the C codec and the Python mirror? **Method** `make -C project/protocol/c test`; `pytest project/protocol/python/tests`. **Result** 188 C checks, 3 parity tests, 0 failures. **Reading** Proves layout consistency only; says nothing about air time or range. **Decision** Keep. **Status** kept. **Evidence** `project/protocol`.

## RES-SYS-2 — Box application on a mock HAL
**Question** Does `box_app_wake` behave on quiet, smoke, fire, fault, survival, bad commands? **Method** `make -C project/firmware/box/host test`. **Result** 969 checks pass. **Reading** Logic only: no real sensor, radio, power or time. The ESP-IDF layer was **not compiled**. **Decision** Keep; build on hardware next. **Status** kept. **Evidence** `project/firmware/box/host`.

## RES-SYS-3 — Bridge core and SIM800 driver
**Question** Do ack, forwarding, SBC power control and the emergency SMS rule work? **Method** host tests with scripted radio/UART/modem. **Result** 49 checks pass. **Reading** The modem is a script, not a SIM800L on a network. **Status** kept.

## RES-SYS-4 — Gateway end to end with the real box code
**Question** Do frames produced by the C box firmware drive the right alerts and actions? **Method** `box_sim` scenarios replayed into `Gateway`. **Result** fire: one L3 episode, one drone mission, one SMS per number; quiet: no SMS; fault: L4/L5, not L3. 31 gateway tests pass. **Reading** Timing is the simulator's; fusion rates are placeholders.
**Failures logged along the way:** (a) a flame-absent reading counted as negative evidence and blocked a gas+camera confirmation at extreme danger → absence of flame no longer counts (narrow field of view), test added. (b) A single-box source estimate moved the drone target ~3 km away from the box → source used only with ≥ 4 boxes detecting (matches RES source result 71 % within 500 m only then). **Status** kept.

## Open
Fusion rates and priors need controlled recordings. Everything on hardware is open.
