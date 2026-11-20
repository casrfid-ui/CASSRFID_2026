"""Fast path: cross-box evidence fusion (Bayesian log-odds + sequential probability ratio test), with the FWI as the prior.

Each witness (gas chain, flame, camera, gateway vision) of each box contributes a log-likelihood ratio taken from the LATEST
reading (replaced, not accumulated, so repeated frames are never counted twice). Contributions fade with a time constant
back to zero. The statistic is S = logit(prior(danger)) + sum of LLRs. SPRT: confirm when S >= ln((1-beta)/alpha),
clear when S <= ln(beta/(1-alpha)).

All sensor rates and the prior table are PLACEHOLDERS (config.FusionParams), to be replaced by measured values.
The box's own FIRE decision is never overruled here: fusion can only add confirmation (see alerts.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .ffp import frame as F


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def _llr(tpr: float, fpr: float, positive: bool) -> float:
    if positive:
        return math.log(tpr / fpr)
    return math.log((1 - tpr) / (1 - fpr))


@dataclass
class FusionResult:
    statistic: float
    posterior: float
    llr_sum: float
    prior: float
    danger: int
    confirmed: bool
    suspected: bool
    cleared: bool
    contributions: list = field(default_factory=list)   # (box, witness, llr_now)

    def to_dict(self):
        return {"statistic": round(self.statistic, 3), "posterior": round(self.posterior, 5), "llr_sum": round(self.llr_sum, 3),
                "prior": self.prior, "danger": self.danger, "confirmed": self.confirmed, "suspected": self.suspected,
                "contributions": [{"box": b, "witness": w, "llr": round(v, 3)} for b, w, v in self.contributions]}


class Fusion:
    def __init__(self, params):
        self.p = params
        self.ev: dict[tuple, tuple[float, float]] = {}      # (box, witness) -> (llr, t)
        self.A = math.log((1 - params.beta) / params.alpha)
        self.B = math.log(params.beta / (1 - params.alpha))
        self.confirmed = False

    # ---- evidence intake
    def observe_status(self, box: int, s: F.Status, t: float):
        p = self.p
        if s.warmup or s.scan_bad or s.gas_faults:
            self.ev.pop((box, "gas"), None)
        elif s.gas_class == F.GAS_SMOKE:
            self.ev[(box, "gas")] = (_llr(p.gas_smoke_tpr, p.gas_smoke_fpr, True), t)
        elif s.gas_class == F.GAS_DECOY:
            self.ev[(box, "gas")] = (math.log(p.gas_decoy_tpr / p.gas_decoy_fpr), t)
        else:
            self.ev[(box, "gas")] = (_llr(p.gas_smoke_tpr, p.gas_smoke_fpr, False), t)
        if s.flame:                      # an absent flame is not evidence: the sensor has a narrow field of view
            self.ev[(box, "flame")] = (_llr(p.flame_tpr, p.flame_fpr, True), t)
        else:
            self.ev.pop((box, "flame"), None)
        if s.cam_valid:
            self.ev[(box, "camera")] = (_llr(p.camera_tpr, p.camera_fpr, s.cam_label in (F.CAM_FIRE, F.CAM_SMOKE)), t)

    def observe_vision(self, box: int, label: str, conf: float, t: float):
        """Gateway re-check of the camera frame (stub model until the detector is trained)."""
        p = self.p
        pos = label in ("fire", "smoke")
        # a low-confidence positive counts as no information
        if pos and conf < 0.5:
            self.ev.pop((box, "vision"), None)
            return
        self.ev[(box, "vision")] = (_llr(p.vision_tpr, p.vision_fpr, pos), t)

    def forget_box(self, box: int):
        for k in [k for k in self.ev if k[0] == box]:
            del self.ev[k]

    # ---- evaluation
    def evaluate(self, now: float, danger: int) -> FusionResult:
        p = self.p
        danger = max(0, min(len(p.prior_by_danger) - 1, int(danger)))
        prior = p.prior_by_danger[danger]
        contrib = []
        total = 0.0
        for (box, w), (llr, t) in list(self.ev.items()):
            f = math.exp(-max(0.0, now - t) / p.decay_s)
            if f < 0.01:
                del self.ev[(box, w)]
                continue
            v = llr * f
            contrib.append((box, w, v))
            total += v
        S = _logit(prior) + total
        post = 1 / (1 + math.exp(-S))
        if S >= self.A:
            self.confirmed = True
        elif S <= self.B:
            self.confirmed = False
        return FusionResult(S, post, total, prior, danger, self.confirmed, post >= p.p_suspect, S <= self.B, contrib)
