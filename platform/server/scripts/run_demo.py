#!/usr/bin/env python3
"""Hardware-free live demo: the real gateway application (project/gateway) runs here, fed by the scripted forest scenario
(real 16-byte frames), and the dashboard backend + web UI run beside it.

  python scripts/run_demo.py                 # pull mode: the dashboard polls the gateway API on 127.0.0.1:8090
  python scripts/run_demo.py --push          # push mode: the gateway uplinks its snapshot (NAT-friendly path)
  python scripts/run_demo.py --speed 2       # story twice as fast
Then open http://127.0.0.1:3000 . Acknowledge the fire on the dashboard to see the recovery."""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

import uvicorn                                                    # noqa: E402

from ffn_dashboard.api import create_app                          # noqa: E402
from ffn_dashboard.config import load_config                      # noqa: E402
from ffn_dashboard.demo import scenario as S                      # noqa: E402
from ffn_dashboard.service import Service                         # noqa: E402
from ffn_gateway import uart_link as U                            # noqa: E402
from ffn_gateway.api import serve                                 # noqa: E402
from ffn_gateway.app import Gateway                               # noqa: E402
from ffn_gateway.config import load_config as gw_config           # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--gw-port", type=int, default=8090)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--push", action="store_true", help="gateway pushes snapshots instead of being polled")
    ap.add_argument("--db", default="", help="dashboard database (default: a temporary file)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    tmp = Path(tempfile.mkdtemp(prefix="ffn_demo_"))

    gcfg = gw_config(None, S.demo_gateway_config(f"http://127.0.0.1:{a.port}", a.gw_port, str(tmp / "missions"),
                                                 push_s=3.0 if a.push else 0.0))
    gw = Gateway(gcfg, U.Link(U.MemoryLink()))
    serve(gw)
    scen = S.Scenario(speed=a.speed)

    def gateway_loop():
        last_tick = 0.0
        while True:
            now = time.time()
            try:
                for m in scen.step(now, gw):
                    gw.handle(m, now)
                if now - last_tick >= 1.0:
                    gw.tick(now)
                    last_tick = now
            except Exception:
                logging.exception("demo gateway loop")
            time.sleep(0.25)

    threading.Thread(target=gateway_loop, name="demo-gateway", daemon=True).start()

    dcfg = load_config(None, {
        "port": a.port, "db_path": a.db or str(tmp / "dashboard.db"), "poll_s": 2.0,
        "gateway_url": "" if a.push else f"http://127.0.0.1:{a.gw_port}", "gateway_token": "demo-gateway",
        "ingest_token": "demo-ingest", "site_name": "Demo site · 7 boxes, scripted scenario",
        "drone_base": {"lat": S.DRONE_BASE[0], "lon": S.DRONE_BASE[1]},
        "gateway_pos": {"lat": S.GATEWAY_POS[0], "lon": S.GATEWAY_POS[1]},
        "spare_gateway_pos": {"lat": S.SPARE_GATEWAY[0], "lon": S.SPARE_GATEWAY[1]}, "push_offline_after_s": 15.0})
    svc = Service(dcfg)
    print(f"\n  Dashboard: http://127.0.0.1:{a.port}   (gateway API: http://127.0.0.1:{a.gw_port}, mode: {'push' if a.push else 'pull'})\n")
    uvicorn.run(create_app(svc), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
