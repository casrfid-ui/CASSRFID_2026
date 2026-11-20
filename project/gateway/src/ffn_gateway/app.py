"""The gateway application: wires link, ingest, fusion, alerts, dispatch, downlink and the slow path together.

`Gateway` is clock-injected (`now` is always a parameter) so tests and simulations are deterministic.
`python -m ffn_gateway --config gateway.json` runs it on the SBC."""
from __future__ import annotations

import argparse
import logging
import queue
import threading
import time

from . import uart_link as U
from .alerts import NAMES, AlertEngine
from .config import GatewayConfig, load_config
from .dispatch import Dispatcher, http_exchange_json
from .downlink import Downlink
from .ffp import frame as F
from .fusion import Fusion
from .models import ModelRegistry
from .registry import Registry
from .slowpath import SlowPath
from .store import Store

log = logging.getLogger("ffn_gateway")


class Gateway:
    def __init__(self, cfg: GatewayConfig, link: U.Link | None = None, poster=None, store: Store | None = None, load_models: bool = True,
                 exchanger=http_exchange_json):
        self.cfg = cfg
        self.link = link
        self.store = store or Store(cfg.db_path)
        self.reg = Registry(cfg)
        self.fusion = Fusion(cfg.fusion)
        self.alerts = AlertEngine(cfg, self.store)
        kw = {"poster": poster} if poster else {}
        self.disp = Dispatcher(cfg, self.store, link, **kw)
        self.down = Downlink(cfg, self.store, link)
        self.models = ModelRegistry(cfg)
        if load_models:
            self.models.load()
        self.slow = SlowPath(cfg, self.reg, self.models, self.store, lambda: self.alerts.last)
        self.seen: dict[tuple, float] = {}
        self.stats = {"rx": 0, "bad": 0, "dup": 0, "emergency": 0}
        self.bridge_status: U.BridgeStatus | None = None
        self.bridge_sms_t: dict[int, float] = {}
        self.known: dict[tuple, str] = {}          # (level, box) -> reason currently active
        self.episode: str | None = None
        self.last_level_sent = -1
        self.last_time_sync = 0.0
        self.last_slow = 0.0
        self.fusion_result = None
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self.exchanger = exchanger
        self.last_push = 0.0
        self.last_pushed_event = 0
        self._pushing = False
        self.uplink = {"ok": 0, "fail": 0, "error": "", "commands": 0}

    # ------------------------------------------------------------ ingest
    def handle(self, msg, now: float):
        with self.lock:
            if isinstance(msg, U.RxFrame):
                self.on_rx(msg, now)
            elif isinstance(msg, U.BridgeStatus):
                self.bridge_status = msg
            elif isinstance(msg, U.Emergency):
                self.stats["emergency"] += 1
                self.bridge_sms_t[msg.box] = now
                self.store.add_event("sms", f"bridge sent {msg.n_numbers} emergency SMS for box {msg.box}", box=msg.box, level=3, t=now)
            elif isinstance(msg, U.SmsResult):
                self.store.add_event("sms_result", f"sms {msg.id} status {msg.status}", level=0, data={"id": msg.id, "status": msg.status}, t=now)

    def on_rx(self, m: U.RxFrame, now: float):
        try:
            fr = F.decode(m.wire)
        except F.FrameError as e:
            self.stats["bad"] += 1
            self.store.add_event("bad_frame", f"undecodable frame: {e}", t=now)
            return
        if fr.type not in F.BOX_TYPES:
            return
        key = fr.key()
        first = key not in self.seen or now - self.seen[key] > self.cfg.dedupe_window_s
        self.seen[key] = now
        if len(self.seen) > 2000:
            self.seen = {k: t for k, t in self.seen.items() if now - t < self.cfg.dedupe_window_s}
        self.stats["rx"] += 1
        self.store.add_frame(now, fr.origin, fr.type, fr.seq, m.rssi, m.snr, m.wire, fr.flags)
        if not first:
            self.stats["dup"] += 1
            return
        box = self.reg.update(fr, m.rssi, m.snr / 4.0, now)
        if fr.type in (F.T_ALERT, F.T_STATE, F.T_HEARTBEAT, F.T_LAST_GASP):
            self.fusion.observe_status(fr.origin, box.last_status, now)
        self.evaluate(now)

    def on_camera_event(self, box: int, label: str, conf: float, ms: float, now: float):
        """Called by the vision service when the gateway re-checked a camera frame."""
        with self.lock:
            b = self.reg.get(box)
            b.vision = {"label": label, "conf": conf, "ms": ms, "t": now}
            self.fusion.observe_vision(box, label, conf, now)
            self.store.add_event("vision", f"vision box {box}: {label} {conf:.2f}", box=box, data=b.vision, t=now)
            self.evaluate(now)

    # ------------------------------------------------------------ decisions
    def evaluate(self, now: float):
        with self.lock:
            fresh = self.reg.fresh_boxes(now, 2 * self.cfg.heartbeat_s)
            danger = max((b.last_status.danger for b in fresh if b.last_status and not b.last_status.provisional), default=1)
            self.fusion_result = self.fusion.evaluate(now, danger)
            a = self.alerts.evaluate(now, self.reg, self.fusion_result)
            active = {(x.level, x.box): x for x in a.alerts}
            for k, x in active.items():
                if k not in self.known:
                    self._raise(x, now)
                self.known[k] = x.reason
            for k in [k for k in self.known if k not in active]:
                self.store.add_event("cleared", f"{NAMES[k[0]]} box {k[1]} cleared", box=k[1], level=k[0], t=now)
                del self.known[k]
            if not a.fire_boxes and self.episode and not self.alerts.fire_latched:
                self.episode = None
            if a.top != self.last_level_sent and self.link:
                self.link.send(U.set_level(a.top))
                self.last_level_sent = a.top
            return a

    def _pos(self, box: int):
        b = self.reg.get(box) if box else None
        if b and (b.lat or b.lon):
            return b.lat, b.lon
        for bb in self.reg.boxes.values():
            if bb.lat or bb.lon:
                return bb.lat, bb.lon
        return 0.0, 0.0

    def _raise(self, x, now):
        lat, lon = self._pos(x.box)
        if x.level == 3:
            if self.episode is None:
                self.episode = f"F{int(now)}"
                new_episode = True
            else:
                new_episode = False
            bridge_done = any(now - t < 180 for t in self.bridge_sms_t.values())
            self.disp.notify(self.episode, 3, x.box, x.reason, lat, lon, now=now, sms=not bridge_done)
            if self.link:
                for bx in self.alerts.fire_boxes:
                    self.link.send(U.dispatched(bx))
            if new_episode:
                self.slow.run_once(now)           # source / isochrones for the dashboard and the drone target
                src = self.slow.results.get("fire", {}).get("source")
                use = src and src.get("used_as_ignition")
                self.disp.drone(self.episode, src["lat"] if use else lat, src["lon"] if use else lon, now)
        else:
            self.disp.notify(f"{NAMES[x.level][:2]}-{int(now)}-{x.box}", x.level, x.box, x.reason, lat, lon, now=now, sms=False)
            if x.level == 4:
                self.down.neighbours_to_alert(self.reg, x.box, now)

    def acknowledge(self, now: float):
        with self.lock:
            self.alerts.acknowledge(now)
            for bx in list(self.alerts.fire_boxes):
                self.down.reset_fire(bx, now)
            self.store.add_event("operator", "operator acknowledged the fire", level=3, t=now)
            return self.evaluate(now)

    # ------------------------------------------------------------ operator commands (HTTP API and dashboard uplink)
    def run_command(self, name: str, body: dict, now: float) -> dict:
        """One entry point for every operator action. Raises KeyError / ValueError on a bad body."""
        with self.lock:
            d = self.down
            if name == "ack":
                return self.acknowledge(now).to_dict()
            if name == "test_sms":
                self.disp.sms("test-" + str(int(now)), 0, str(body.get("text", "Test SMS from the gateway")), now, force=True)
                return {"ok": True, "numbers": len(self.cfg.phone_numbers)}
            box = int(body["box"])
            if name == "ping": d.ping(box, now)
            elif name == "force_alert": d.force_alert(box, now, "operator")
            elif name == "reset_fire": d.reset_fire(box, now)
            elif name == "thresholds":
                d.set_thresholds(box, float(body["smoke_on"]), float(body["smoke_off"]), float(body["camera"]), now, "operator")
            elif name == "sim_weather":
                d.sim_weather(box, bool(body.get("enable", True)), int(body.get("wind_kmh", 10)),
                              int(round(float(body.get("rain_mm", 0)) * 10)), now)
                return {"ok": True, "note": "delivered at the box's next transmission"}
            else:
                raise ValueError("unknown command " + str(name))
            return {"ok": True}

    def push_uplink(self, now: float) -> dict | None:
        """Send the snapshot (and the new timeline rows) to the dashboard; run the commands it answers with."""
        if not self.cfg.dashboard_url:
            return None
        with self.lock:
            snap = self.snapshot(now)
            rows = [e for e in self.store.events(200) if e["id"] > self.last_pushed_event]
            body = {"status": snap, "timeline": rows, "risk": self.slow.results, "models": self.models.status}
        try:
            ans = self.exchanger(self.cfg.dashboard_url.rstrip("/") + "/api/gateway/snapshot", body, self.cfg.dashboard_token)
        except Exception as e:
            self.uplink["fail"] += 1
            self.uplink["error"] = repr(e)[:200]
            return None
        self.uplink["ok"] += 1
        self.uplink["error"] = ""
        if rows:
            self.last_pushed_event = max(e["id"] for e in rows)
        for c in (ans or {}).get("commands", []):
            try:
                self.run_command(c["name"], c.get("body") or {}, now)
                self.uplink["commands"] += 1
                self.store.add_event("operator", f"dashboard command {c['name']} {c.get('body') or ''}", box=int((c.get('body') or {}).get('box', 0) or 0), t=now)
            except (KeyError, ValueError) as e:
                self.store.add_event("operator", f"dashboard command {c.get('name')} refused: {e}", t=now)
        return ans

    def _push_bg(self, now: float):
        try:
            self.push_uplink(now)
        finally:
            self._pushing = False

    # ------------------------------------------------------------ periodic
    def start_session(self, now: float):
        if not self.link:
            return
        if self.cfg.phone_numbers:
            self.link.send(U.set_numbers(self.cfg.phone_numbers))
        self.sync_time(now)

    def sync_time(self, now: float):
        if self.link and now > 1.7e9:
            self.link.send(U.set_time(int(now), self.cfg.utc_offset_min // 15))
            self.last_time_sync = now

    def tick(self, now: float):
        with self.lock:
            self.evaluate(now)
            self.down.apply_threshold_policy(self.reg, now)
            self.disp.flush(now)
            if now - self.last_time_sync > 3600:
                self.sync_time(now)
            if now - self.last_slow >= self.cfg.slow_path_period_s:
                self.last_slow = now
                self.slow.run_once(now)
            if self.cfg.dashboard_push_s > 0 and now - self.last_push >= self.cfg.dashboard_push_s and not self._pushing:
                self.last_push = now
                self._pushing = True
                threading.Thread(target=self._push_bg, args=(now,), name="uplink", daemon=True).start()

    # ------------------------------------------------------------ views
    def snapshot(self, now: float) -> dict:
        with self.lock:
            a = self.alerts.last
            return {"t": now, "gateway_id": self.cfg.gateway_id, "assessment": a.to_dict(),
                    "fusion": self.fusion_result.to_dict() if self.fusion_result else None,
                    "boxes": [b.to_dict(now) for b in self.reg.boxes.values()],
                    "bridge": vars(self.bridge_status) if self.bridge_status else None,
                    "stats": dict(self.stats), "episode": self.episode, "uplink": dict(self.uplink),
                    "outbox_pending": len(self.store.outbox_pending())}

    # ------------------------------------------------------------ run loop
    def run(self):
        self.start_session(time.time())
        while not self._stop.is_set():
            try:
                msg = self.link.inbox.get(timeout=1.0) if self.link else None
                if msg is not None:
                    self.handle(msg, time.time())
                self.tick(time.time())
            except queue.Empty:
                self.tick(time.time())
            except Exception:                    # the loop must survive anything
                log.exception("loop error")

    def stop(self):
        self._stop.set()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ffn_gateway")
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(a.config)
    link = None
    if cfg.serial_port:
        try:
            link = U.Link(U.SerialLink(cfg.serial_port, cfg.serial_baud))
        except Exception as e:
            raise SystemExit(f"cannot open the bridge serial port {cfg.serial_port!r}: {e}")
        link.start()
    else:
        log.warning("no serial_port configured: running without the bridge (simulation / API only)")
    try:
        gw = Gateway(cfg, link)
    except Exception as e:
        raise SystemExit(f"cannot start (database path {cfg.db_path!r}?): {e}")
    if not a.no_api:
        from .api import serve
        serve(gw)
    try:
        gw.run()
    except KeyboardInterrupt:
        pass
    finally:
        if link:
            link.stop()


if __name__ == "__main__":
    main()
