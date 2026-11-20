"""Protocol v1 (gateway side)."""
import json


def ok(req_id, label, conf, ms, boxes=None):
    d = {"v": 1, "id": int(req_id), "label": label, "conf": round(float(conf), 4), "ms": int(ms)}
    if boxes is not None:                                   # debug only (?debug=1): the box never asks for it
        d["boxes"] = [[b[0], round(b[1], 4), *[round(v, 1) for v in b[2:]]] for b in boxes]
    return json.dumps(d, separators=(",", ":"))


def error(req_id, message):
    return json.dumps({"v": 1, "id": int(req_id), "error": message}, separators=(",", ":"))
