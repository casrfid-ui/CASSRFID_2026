# gateway — SBC application (`ffn_gateway`)
See [FICHE.md](FICHE.md). Quick start:
```
cd project/gateway
python3 -m pytest -q                                  # 34 tests
python3 scripts/replay_box_sim.py                     # fire scenario from the real C box code, readable timeline
cp config/gateway.example.json config/gateway.json    # edit numbers, positions, serial port
PYTHONPATH=src:../protocol/python python3 -m ffn_gateway --config config/gateway.json
```
Models: set paths in `models` (relative to `ai-data/`). Empty or missing = the slot is reported by `GET /v1/models` as `placeholder`/`unavailable` and the app keeps running. To plug the trained camera model or the autoencoder later, drop the file in and set its path; the camera detector itself is served by the vision service, which posts to `/v1/camera-event`.

Dashboard link (`platform/`): set `dashboard_url` and `dashboard_token` (= the dashboard's `ingest_token`). Alerts, drone
missions and emails are pushed through the outbox with retry. The dashboard reads the state either by polling this API
(`api_token` = its `gateway_token`, same LAN) or, behind a mobile operator's NAT, with `dashboard_push_s` > 0: the gateway
posts its snapshot to `/api/gateway/snapshot` every N seconds and runs the operator commands returned in the answer.
