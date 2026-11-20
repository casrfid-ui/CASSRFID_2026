# platform — operator dashboard

The human side of the network: a live **Network** view of the whole chain (boxes, LoRa mesh, ESP32 bridge, SBC, modem, 2G/GSM, dashboard, operator, drone) with traffic on each link, an illustrated forest map (canopy, relief, trail, stream, clearings; burning and threatened canopy and smoke drift during a fire), alert banner and panel (L1 to L5), action timeline, per-box health and
history, evidence fusion, fire-spread isochrones, drone mission, fire-weather forecast, system health and operator commands.
It never decides an alert (boxes and the gateway do) and the network keeps working without it. See [FICHE.md](FICHE.md).

```
platform/
  server/   FastAPI backend (ffn_dashboard): gateway ingest, operator API, live stream (SSE), SQLite, email
  web/      React + TypeScript + Vite UI (served by the backend once built)
```

## Run the live demo (no hardware)
The real gateway application (`project/gateway`) runs in-process, fed by a scripted forest scenario written as real
16-byte frames; the dashboard polls it like it would on the bench.
```bash
cd platform/server
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/run_demo.py                          # http://127.0.0.1:3000   (--push : NAT path, --speed 3 : faster)
```
Story on 7 boxes (the protocol allows box ids 1 to 7 per gateway), about 600 m apart on forested hills, gateway on the
ridge, drone base on the forest road, spare gateway in standby. Boxes 1 and 5 are heard through a neighbour (mesh relay).
High fire weather (L1) at 30 s; box 1 goes silent at 40 s (L4 about 100 s later); smoke on box 6 at 80 s (L2); the plume
reaches box 7 (L2) and box 2; fire on box 6 at 110 s (L3: SMS, email, drone mission, spread isochrones); box 4 battery low
at 150 s (L5). Acknowledge on the banner; boxes 6 and 7 return to Normal 25 s later. Positions are illustrative: edit
`SITES` in `src/ffn_dashboard/demo/scenario.py` (or use real GPS fixes) to place the boxes on your site.
Wind and rain are simulated and shown as such everywhere. In the demo the bridge status is also simulated (no serial link).

## Run against a real gateway
```bash
cd platform/web && npm install && npm run build      # once: builds web/dist, served by the backend
cd ../server && cp config/dashboard.example.json config/dashboard.json   # set gateway_url/tokens, SMTP, site
python -m ffn_dashboard --config config/dashboard.json
```
UI development with hot reload: run the backend, then `cd platform/web && npm run dev` (http://127.0.0.1:5173, `/api` proxied).

| Setting | Meaning |
|---|---|
| `gateway_url`, `gateway_token` | pull mode: the gateway HTTP API and its `api_token`; empty URL = push mode only |
| `ingest_token` | must equal the gateway's `dashboard_token`; checked on every gateway POST |
| `operator_token` | when set, every `/api/ops/*` action needs it (entered once in System → Operator access) |
| `smtp.*` | alert emails; without a host they are recorded as `logged` |
| `drone_base`, `gateway_pos`, `spare_gateway_pos`, `site_name`, `timezone` | drawn on the map, used for times |
| `map_tiles` | base maps of the live map (default: OpenStreetMap and OpenTopoMap). The public OSM servers are fine for a demo; an operational deployment should use its own tile server or a provider, per the OSM tile usage policy |

The map runs on Leaflet with OpenStreetMap tiles. If the tiles cannot load (no internet in the field), it switches by itself
to the offline map drawn from the GPS positions; the operator can also pick Offline at any time.

## API
| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/alerts`, `/api/missions`, `/api/email` | gateway outbox | alert, drone mission, email request |
| POST | `/api/gateway/snapshot` | gateway uplink | status + new timeline rows; answer = queued operator commands |
| GET | `/api/overview` | UI | everything the operations view needs, already named for display |
| GET | `/api/stream` | UI | server-sent events: `overview`, `alert`, `event`, `mission`, `email`, `command` |
| GET | `/api/alerts`, `/api/timeline`, `/api/boxes/{id}/series`, `/api/risk`, `/api/missions`, `/api/emails`, `/api/commands`, `/api/config`, `/api/health` | UI | lists and history |
| POST | `/api/ops/ack`, `/api/ops/command`, `/api/ops/sim-weather`, `/api/ops/test-sms`, `/api/ops/test-email` | operator | actions (direct in pull mode, queued in push mode) |

Interactive docs: `http://127.0.0.1:3000/docs`.

## Tests
```bash
cd platform/server && python -m pytest -q     # 13 tests, including the end-to-end story in pull and push mode
```
