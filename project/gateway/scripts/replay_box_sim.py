#!/usr/bin/env python3
"""Replay the C box simulator through the gateway and print the timeline.
  make -C ../firmware/box/host sim
  python scripts/replay_box_sim.py fire 1 120 [quiet 2 120]"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "gateway" / "src"), str(ROOT / "protocol" / "python")]
from ffn_gateway import uart_link as U          # noqa: E402
from ffn_gateway.app import Gateway             # noqa: E402
from ffn_gateway.config import load_config      # noqa: E402

SIM = ROOT / "firmware" / "box" / "host" / "build" / "box_sim"


def main(args):
    rows = []
    for i in range(0, len(args), 3):
        out = subprocess.run([str(SIM), args[i], args[i + 1], args[i + 2]], capture_output=True, text=True, check=True).stdout
        rows += [(float(a), bytes.fromhex(c)) for a, _, c in (ln.split() for ln in out.splitlines())]
    cfg = load_config(None, {"db_path": ":memory:", "phone_numbers": ["+000000000000"],
                             "boxes": [{"id": 1, "lat": 36.80, "lon": 10.10}, {"id": 2, "lat": 36.81, "lon": 10.11}],
                             "drone": {"missions_dir": "/tmp/ffn_missions", "base_lat": 36.79, "base_lon": 10.09}})
    gw = Gateway(cfg, U.Link(U.MemoryLink()))
    for t, w in sorted(rows):
        gw.handle(U.RxFrame(-95, 24, w), t)
        gw.tick(t)
    for e in reversed(gw.store.events(500)):
        if e["kind"] not in ("cmd",):
            print(f"{e['t']:.0f}  {e['kind']:8s} L{e['level']} box{e['box']}  {e['text'][:100]}")
    print("top level:", gw.alerts.last.to_dict())


if __name__ == "__main__":
    main(sys.argv[1:] or ["fire", "1", "120", "quiet", "2", "120"])
