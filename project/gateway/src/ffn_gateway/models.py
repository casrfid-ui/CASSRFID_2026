"""Model registry for the slow path. Loads the ai-data prediction blocks IN PLACE (no copies) by adding their `python/src`
folders to sys.path. A model that is missing or not configured is reported in /v1/models as a pending slot and the application
runs without it, so a trained file is added by editing the config only."""
from __future__ import annotations

import sys
from pathlib import Path

_BLOCKS = {
    "fwi": "box/fwi",
    "gas_chain": "box/gas_chain",
    "gw_common": "gateway/common",
    "risk_gru": "gateway/risk_gru",
    "fwi_forecast": "gateway/fwi_forecast",
    "spread_source": "gateway/spread_source",
    "gas_trend": "gateway/gas_trend",
}
# phase B slots (spec section 6)
PLACEHOLDERS = {
    "autoencoder": "drift / anomaly autoencoder on the gas bands (phase B)",
    "gas_classifier": "larger gas classifier (phase B)",
}


def find_ai_data(configured: str = "") -> Path:
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "ai-data"      # project/gateway/src/ffn_gateway -> repository root


class ModelRegistry:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = find_ai_data(cfg.ai_data_root)
        self.status: dict[str, dict] = {}
        self.risk_cls = self.trend_cls = None
        self.forecaster = None
        self.spread_mod = None
        self._path_blocks()

    def _path_blocks(self):
        for sub in _BLOCKS.values():
            p = self.root / sub / "python" / "src"
            if p.is_dir() and str(p) not in sys.path:
                sys.path.insert(0, str(p))

    def _file(self, key: str):
        rel = self.cfg.models.get(key, "")
        if not rel:
            return None
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def _mark(self, name, state, detail="", provenance=""):
        self.status[name] = {"state": state, "detail": detail, "provenance": provenance}

    def load(self):
        # risk GRU (class; one predictor per box is created by the slow path)
        p = self._file("risk_gru")
        try:
            if p is None:
                raise FileNotFoundError("not configured")
            from risk_gru.predictor import RiskPredictor
            test = RiskPredictor(str(p))
            self.risk_cls, self.risk_path = RiskPredictor, str(p)
            self._mark("risk_gru", "ok", str(p), str(test.provenance))
        except Exception as e:
            self._mark("risk_gru", "unavailable", repr(e))
        # FWI forecast
        p = self._file("fwi_forecast")
        try:
            if p is None:
                raise FileNotFoundError("not configured")
            from fwi_forecast.climate import Climate
            from fwi_forecast.forecaster import FwiForecaster
            self.forecaster = FwiForecaster(Climate.from_json(p.read_text()))
            self._mark("fwi_forecast", "ok", str(p), "synthetic climate" if "synthetic" in p.name else "")
        except Exception as e:
            self._mark("fwi_forecast", "unavailable", repr(e))
        # spread + source (no weights: physics)
        try:
            import spread_source.spread as sp
            import spread_source.source as so
            self.spread_mod, self.source_mod = sp, so
            self._mark("spread_source", "ok", "physics model: wind, slope, ISI", "default fuel constants")
        except Exception as e:
            self._mark("spread_source", "unavailable", repr(e))
        # gas trend
        p = self._file("gas_trend")
        try:
            if p is None:
                raise FileNotFoundError("not configured")
            from gas_trend.predictor import TrendPredictor
            TrendPredictor(str(p))
            self.trend_cls, self.trend_path = TrendPredictor, str(p)
            self._mark("gas_trend", "ok", str(p), "demo model, recorded burns")
        except Exception as e:
            self._mark("gas_trend", "unavailable", repr(e))
        for name, why in PLACEHOLDERS.items():
            p = self._file(name)
            if p is not None and p.exists():
                self._mark(name, "file-present", f"{p} found but no runtime wrapper yet: {why}")
            else:
                self._mark(name, "placeholder", why)
        return self.status
