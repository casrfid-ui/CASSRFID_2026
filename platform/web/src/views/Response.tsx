import { useEffect, useState } from "react";
import type { AppConfig, Overview, RiskView } from "../lib/types";
import { api } from "../lib/api";
import { area, coord, num, stamp } from "../lib/format";
import { Card, Empty } from "../components/ui";
import { ForecastChart } from "../components/Charts";
import { LiveMap } from "../components/LiveMap";

const CMD: Record<number, string> = { 22: "Take off", 16: "Fly to waypoint", 183: "Release payload", 20: "Return to launch" };

function distM(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const k = Math.PI / 180, R = 6371000;
  const dLat = (b.lat - a.lat) * k, dLon = (b.lon - a.lon) * k;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * k) * Math.cos(b.lat * k) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function Response({ ov, config }: { ov: Overview; config: AppConfig | null }) {
  const [risk, setRisk] = useState<RiskView | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.risk().then((r) => alive && setRisk(r)).catch(() => undefined);
    load();
    const t = window.setInterval(load, 15000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);
  const m = ov.mission;
  const fire = ov.fire;
  const iso = Object.entries(fire.isochrones ?? {}).sort((a, b) => +a[0] - +b[0]);
  return (
    <main className="page">
      <div className="row2">
        <Card title="Drone mission" sub={m ? `${m.id} · built ${stamp(m.created ?? m.received ?? ov.t)}` : undefined} id="h-drone"
              right={m ? <span className="badge lv lv-4">Simulated flight</span> : undefined} flush>
          {!m ? <Empty>No mission. The gateway builds one when a fire is confirmed (L3).</Empty> : (
            <>
              <div className="card-b">
                <div className="kv" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
                  <div><div className="k">Target</div><div className="v" style={{ fontSize: 13 }}>{coord(m.target.lat, m.target.lon)}</div></div>
                  <div><div className="k">Distance from base</div><div className="v">{num(distM(m.base, m.target) / 1000, 2)}<small> km</small></div></div>
                  <div><div className="k">Cruise altitude</div><div className="v">{m.items.find((i) => i.alt)?.alt ?? "–"}<small> m</small></div></div>
                </div>
              </div>
              <table className="tbl">
                <thead><tr><th>#</th><th>Step</th><th>MAVLink</th><th>Detail</th></tr></thead>
                <tbody>
                  {m.items.map((it) => (
                    <tr key={it.seq}>
                      <td className="mono">{it.seq}</td><td>{CMD[it.command] ?? it.name}</td><td className="mono">{it.command}</td>
                      <td className="mono muted">{it.lat != null ? `${it.lat.toFixed(5)}, ${it.lon?.toFixed(5)} · ${it.alt} m` : it.servo != null ? `servo ${it.servo} → ${it.pwm} µs` : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="card-b" style={{ paddingTop: 12 }}><span className="note">{m.note ?? "Mission file written by the gateway; the real mini release mechanism is built, the flight is simulated."}</span></div>
            </>
          )}
        </Card>
        <Card title="Fire spread" sub="slow path · grid model driven by wind" id="h-spread" flush>
          {!iso.length ? <Empty>No active fire: isochrones appear when a fire is confirmed.</Empty> : (
            <>
              <table className="tbl">
                <thead><tr><th>Horizon</th><th className="r">Area reached</th></tr></thead>
                <tbody>{iso.map(([k, v]) => <tr key={k}><td>{k} min</td><td className="r mono">{area(v.area_m2)}</td></tr>)}</tbody>
              </table>
              <div className="card-b" style={{ paddingTop: 12 }}>
                <dl className="kv-list">
                  <dt>Wind</dt><dd>{num(fire.wind_kmh ?? null, 0)} km/h toward {num(fire.wind_to_deg ?? null, 0)}°{fire.wind_direction_simulated ? " (direction simulated)" : ""}</dd>
                  {fire.source && <><dt>Source estimate</dt><dd>{coord(fire.source.lat, fire.source.lon)} · 50 % area {area(fire.source.area50_m2)}
                    <div className="note">{fire.source.used_as_ignition ? `Used as the ignition point and drone target: ${fire.source.n_boxes_detecting} boxes are in the plume.` : `Indicative only: ${fire.source.n_boxes_detecting} boxes detect, 4 are needed. The drone targets the box position.`}</div></dd></>}
                </dl>
              </div>
            </>
          )}
        </Card>
      </div>

      {iso.length > 0 && <Card title="Spread on the site" flush id="h-spreadmap"><LiveMap ov={ov} config={config} height={480} /></Card>}

      <Card title="Fire weather forecast" sub="gradient boosting, 1 to 3 days ahead · bar = 10 to 90 % range, line = median" id="h-fc">
        {!risk || !Object.keys(risk.fwi_forecast).length ? <Empty>No forecast yet: it needs a day of weather from the boxes.</Empty> : (
          <div className="row2">
            {Object.entries(risk.fwi_forecast).map(([id, days]) => {
              const b = ov.boxes.find((x) => x.id === +id);
              return (
                <div key={id} className="stack" style={{ gap: 6 }}>
                  <div className="inline" style={{ justifyContent: "space-between" }}>
                    <b>{b?.name ?? `Box ${id}`}</b>
                    <span className="note">chance of high danger or worse tomorrow: <b className="mono">{Math.round(days[0].p_high * 100)} %</b></span>
                  </div>
                  <ForecastChart days={days} label={`FWI forecast for ${b?.name ?? id}`} />
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </main>
  );
}
