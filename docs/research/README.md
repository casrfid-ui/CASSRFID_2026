# Research log (v2)

One file per domain. Every experiment is logged, failures included. A decision without an entry has no evidence.

| File | Domain | IDs |
|---|---|---|
| [box-gas-chain.md](box-gas-chain.md) | Box gas chain | RES-GAS-n |
| [box-fwi.md](box-fwi.md) | Box FWI engine | RES-FWI-n |
| [box-state-machine.md](box-state-machine.md) | Box state machine | RES-SM-n |
| [box-flame.md](box-flame.md) | Box flame sensor | RES-FL-n |
| [box-runtime.md](box-runtime.md) | Box runtime and C ports | RES-RT-n |
| [box-camera.md](box-camera.md) | Box camera and gateway vision | RES-CAM-n |
| [project-system.md](project-system.md) | Project firmware, protocol and gateway app | RES-SYS-n |

## Entry format
**Question** · **Method** (command, data, sample size) · **Result** · **Reading** (what it does not prove) · **Decision** · **Status** (`kept`, `superseded`, `open`) · **Evidence**.

## Honesty rules
- Say how many burns, episodes and scans stand behind a number. Two burns are two burns.
- Mendeley is BME688/690 outdoors at ~100 m. The target is a BME680. Every result says so.
- Semi-synthetic steps (dilution) are named as such.
- Assumed numbers are named as assumptions.

## Gateway prediction blocks
Logs in `../../ai-data/docs/research/` (`gateway-risk-gru.md`, `gateway-fwi-forecast.md`, `gateway-spread-source.md`, `gateway-gas-trend.md`).
