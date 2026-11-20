"""Trains the DEMO model on the synthetic world S1 and writes models/risk_gru_demo_synthetic.npz.
It exists to exercise the gateway code path. It has never seen a real fire and must not be shown as a result."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE.parents[2] / "common/python/src"), str(HERE.parents[3] / "box/fwi/python/src")]
from risk_gru import experiments as E  # noqa: E402
from risk_gru.train import save_deployable  # noqa: E402

if __name__ == "__main__":
    r = E.run_synthetic(200, seed=0, gru_seeds=3, epochs=60)
    out = HERE.parents[1] / "models" / "risk_gru_demo_synthetic.npz"
    save_deployable(out, r["model"], r["calib"], r["thr"],
                    "DEMO trained on synthetic seasons (200, seed 0). Never saw a real fire. Not for field use.")
    print(out, out.stat().st_size, "bytes", r["model"].n_params(), "parameters", r["thr"])
