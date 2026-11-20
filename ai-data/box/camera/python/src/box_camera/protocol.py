"""Protocol v1 between box and gateway (reference of cam_parse_response / cam_build_headers)."""
import json

LABELS = {"background": 0, "fire": 1, "smoke": 2}
NAMES = {v: k for k, v in LABELS.items()}


class ProtocolError(ValueError):
    pass


def build_headers(box_id, req_id, unix_s, reasons):
    return (f"X-Box-Id: {box_id}\r\nX-Req-Id: {req_id}\r\nX-Time: {unix_s}\r\n"
            f"X-Reasons: {reasons}\r\nContent-Type: image/jpeg\r\n")


def build_response(req_id, label, conf, ms=None):
    d = {"v": 1, "id": int(req_id), "label": label, "conf": round(float(conf), 4)}
    if ms is not None:
        d["ms"] = int(ms)
    return json.dumps(d, separators=(",", ":"))


def build_error(req_id, message):
    return json.dumps({"v": 1, "id": int(req_id), "error": message}, separators=(",", ":"))


def parse_response(body, expect_id):
    """Return (label_int, conf, model_ms or -1). Raises ProtocolError with code -1 (malformed), -2 (stale), -3 (error)."""
    try:
        d = json.loads(body)
    except Exception:
        raise ProtocolError(-1)
    if not isinstance(d, dict) or d.get("v") != 1 or not isinstance(d.get("id"), int) or isinstance(d.get("id"), bool):
        raise ProtocolError(-1)
    if d["id"] != expect_id:
        raise ProtocolError(-2)
    if "error" in d:
        raise ProtocolError(-3)
    lab, conf = d.get("label"), d.get("conf")
    if lab not in LABELS or isinstance(conf, bool) or not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        raise ProtocolError(-1)
    ms = d.get("ms")
    return LABELS[lab], float(conf), (int(ms) if isinstance(ms, int) and 0 <= ms < 1000000 else -1)
