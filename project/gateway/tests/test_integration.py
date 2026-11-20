"""End to end: real frames produced by the C box firmware (host simulator) are fed to the gateway application.
Skipped when the simulator is not built (make -C project/firmware/box/host sim) ."""
import shutil
import subprocess
from pathlib import Path

import pytest

from ffn_gateway import uart_link as U
from ffn_gateway.ffp import frame as F

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "firmware" / "box" / "host" / "build" / "box_sim"
HDLC_C = ROOT / "firmware" / "gateway_bridge" / "core"

pytestmark = pytest.mark.skipif(not SIM.exists(), reason="box_sim not built")


def run_sim(scenario, box, wakes):
    out = subprocess.run([str(SIM), scenario, str(box), str(wakes)], capture_output=True, text=True, check=True).stdout
    rows = []
    for ln in out.splitlines():
        t, b, hx = ln.split()
        rows.append((float(t), int(b), bytes.fromhex(hx)))
    return rows


def replay(gw, rows):
    for t, _, wire in sorted(rows):
        gw.handle(U.RxFrame(-95, 24, wire), t)
        gw.tick(t)


def test_quiet_day_no_alert_but_housekeeping(gw):
    replay(gw, run_sim("quiet", 1, 60) + run_sim("quiet", 2, 60))
    top = gw.alerts.last.top
    assert top in (0, 1, 5)                      # nothing above maintenance / high risk
    assert gw.stats["bad"] == 0 and gw.reg.get(1).frames > 10 and gw.reg.get(2).frames > 10
    assert not [e for e in gw.store.events() if e["kind"] == "sms"]


def test_fire_scenario_reaches_l3_and_dispatches(gw):
    rows = run_sim("fire", 1, 120) + run_sim("quiet", 2, 120)
    replay(gw, rows)
    assert gw.stats["bad"] == 0
    assert 3 in {a.level for a in gw.alerts.last.alerts}
    kinds = [e["kind"] for e in gw.store.events()]
    assert kinds.count("drone") == 1                         # one mission per episode, not one per repeated frame
    assert len(gw.link.t.take_sent(U.SB_SEND_SMS)) == 2      # two numbers, once


def test_fault_scenario_gives_l4_and_l5(gw):
    replay(gw, run_sim("fault", 1, 120))
    lv = {a.level for a in gw.alerts.last.alerts}
    assert 5 in lv or 4 in lv
    assert 3 not in lv


def test_c_and_python_hdlc_agree(tmp_path):
    cc = shutil.which("gcc")
    if not cc:
        pytest.skip("no gcc")
    src = tmp_path / "t.c"
    src.write_text('#include "hdlc.h"\n#include <stdio.h>\nint main(){uint8_t p[]={0x7E,0x7D,1,2,3};uint8_t o[64];int n=hdlc_encode(0x81,p,5,o,64);for(int i=0;i<n;i++)printf("%02x",o[i]);printf("\\n");return 0;}')
    exe = tmp_path / "t"
    subprocess.run([cc, "-I", str(HDLC_C / "include"), str(src), str(HDLC_C / "src" / "hdlc.c"), "-o", str(exe)], check=True)
    c_hex = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.strip()
    assert c_hex == U.encode(0x81, bytes([0x7E, 0x7D, 1, 2, 3])).hex()
