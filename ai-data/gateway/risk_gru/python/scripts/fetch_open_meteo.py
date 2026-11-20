"""Downloads daily weather (ERA5 reanalysis via Open-Meteo archive API) for a point. Run on a PC with internet.
    python scripts/fetch_open_meteo.py --lat 36.8 --lon 10.1 --start 2015-01-01 --end 2024-12-31 --out weather.csv
Fire labels: download NASA FIRMS hotspots (VIIRS/MODIS) for the same area from https://firms.modaps.eosdis.nasa.gov/download/
and pass both CSV files to risk_gru.datasets.from_weather_and_hotspots. NOT run in the development sandbox (no access)."""
import argparse
import csv
import json
import urllib.parse
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--lat", type=float, required=True)
ap.add_argument("--lon", type=float, required=True)
ap.add_argument("--start", required=True)
ap.add_argument("--end", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
q = urllib.parse.urlencode(dict(latitude=a.lat, longitude=a.lon, start_date=a.start, end_date=a.end, timezone="auto",
                                daily="temperature_2m_max,relative_humidity_2m_min,wind_speed_10m_max,precipitation_sum"))
with urllib.request.urlopen("https://archive-api.open-meteo.com/v1/archive?" + q, timeout=60) as r:
    d = json.load(r)["daily"]
with open(a.out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "temp", "rh", "wind", "rain"])
    for row in zip(d["time"], d["temperature_2m_max"], d["relative_humidity_2m_min"], d["wind_speed_10m_max"], d["precipitation_sum"]):
        w.writerow(row)
print("wrote", a.out)
