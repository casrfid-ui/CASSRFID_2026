"""`python -m ffn_dashboard --config dashboard.json` runs the dashboard backend (and serves the built web UI)."""
from __future__ import annotations

import argparse
import logging

import uvicorn

from .api import create_app
from .config import load_config
from .service import Service


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ffn_dashboard")
    ap.add_argument("--config", default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--gateway-url", default=None, help="pull mode: base URL of the gateway API")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    over = {k: v for k, v in (("host", a.host), ("port", a.port), ("gateway_url", a.gateway_url)) if v is not None}
    cfg = load_config(a.config, over)
    try:
        svc = Service(cfg)
    except Exception as e:
        raise SystemExit(f"cannot open the database {cfg.db_path!r}: {e}")
    uvicorn.run(create_app(svc), host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
