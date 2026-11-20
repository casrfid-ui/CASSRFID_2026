"""Loader of the real smoke data set "Dataset Smoke Detection" (BME688/690, Mendeley Data, DOI 10.17632/48j7mm8k56.1, CC BY 4.0).

Two forms:
- `load_sample()` reads the 1798-scan sample committed in tests/data (no download needed);
- `load_all()` rebuilds complete scans from the 20 CSV files (set CAS_MENDELEY_DIR or pass the folder).

Output layout (one row per scan): gas (ohm), temp (degC), rh (%), dt (s), episode, phase, node, experiment, profile.
Phases are numbered by order: 0 = clean start, 1..7 = consecutive burn phases (the authors' tags are undocumented).
Phase 1 shows no response; phases 3 to 5 hold the strong smoke."""
import glob
import os
import pathlib

import numpy as np

NSTEP = 10
EXPERIMENT = {1: "2021", 2: "2025", 3: "2025", 4: "2025", 5: "2025"}   # node -> burn
MIN_SCANS = 50
HERE = pathlib.Path(__file__).resolve()
SAMPLE = HERE.parents[2] / "tests" / "data" / "real_bme688_sample.npz"
DEFAULT_DIR = HERE.parents[5] / "data" / "Dataset Smoke Detection"


def load_sample(path=SAMPLE):
    """The committed sample, converted to physical units."""
    z = np.load(path, allow_pickle=True)
    d = {k: z[k] for k in ("episode", "phase", "node", "experiment", "profile", "dt")}
    d["gas"] = z["gas"].astype(float)
    d["temp"] = z["temp"] / 100.0
    d["rh"] = z["rh"] / 100.0
    return d


def _scans_of_file(path):
    """Complete 10-step scans of one CSV file, per sensor: list of (time, tag, gas, temp, rh)."""
    import pandas as pd
    df = pd.read_csv(path).sort_values("timestamp_since_poweron")
    per_sensor = {}
    for sid, g in df.groupby("sensor_id"):
        g = g.reset_index(drop=True)
        scan_no = (g.heater_profile_step_index == 0).cumsum()
        rows = []
        for _, s in g.groupby(scan_no):
            if len(s) == NSTEP and list(s.heater_profile_step_index) == list(range(NSTEP)):
                rows.append((int(s.real_time_clock.iloc[0]), int(s.label_tag.mode()[0]),
                             s.resistance_gassensor.values, s.temperature.values, s.relative_humidity.values))
        per_sensor[sid] = rows
    return per_sensor


def load_all(directory=None, min_scans=MIN_SCANS):
    """All files; one episode per (file, sensor). Episodes with fewer than `min_scans` scans are skipped."""
    directory = pathlib.Path(directory or os.environ.get("CAS_MENDELEY_DIR") or DEFAULT_DIR)
    keys = ("gas", "temp", "rh", "dt", "episode", "phase", "node", "experiment", "profile")
    out = {k: [] for k in keys}
    names = []
    for path in sorted(glob.glob(str(directory / "NODE*" / "*.csv"))):
        stem = pathlib.Path(path).stem.replace("__", "_")
        node, profile = int(stem.split("_")[1]), int(stem.split("_")[-1])
        for sid, rows in _scans_of_file(path).items():
            if len(rows) < min_scans:
                continue
            rows.sort(key=lambda r: r[0])
            tags = sorted({r[1] for r in rows if r[1] != 0})
            order = {0: 0, **{t: i + 1 for i, t in enumerate(tags)}}
            times = np.array([r[0] for r in rows])
            dts = np.diff(times, prepend=times[0] - int(np.median(np.diff(times))))
            ep = len(names)
            names.append(f"node{node}_profile{profile}_s{len(names)}")
            for (t, tag, gas, temp, rh), dt in zip(rows, dts):
                out["gas"].append(gas.astype(float)); out["temp"].append(temp.astype(float)); out["rh"].append(rh.astype(float))
                out["dt"].append(max(int(dt), 1)); out["episode"].append(ep); out["phase"].append(order[tag])
                out["node"].append(node); out["experiment"].append(EXPERIMENT[node]); out["profile"].append(profile)
    d = {k: np.array(v) for k, v in out.items()}
    d["kind"] = np.array(names)
    return d
