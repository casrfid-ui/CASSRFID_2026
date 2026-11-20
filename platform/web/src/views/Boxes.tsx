import { useEffect, useState } from "react";
import type { Box, Overview, Sample } from "../lib/types";
import { api } from "../lib/api";
import { ago, cap, clock, coord, num } from "../lib/format";
import { Card, Confirm, Empty, LevelBadge, StatePill } from "../components/ui";
import { DangerScale } from "../components/Panels";
import { LineChart, dangerBands } from "../components/Charts";
import { HealthChips } from "../components/BoxCard";
import type { Toast } from "../lib/live";

type ToastFn = (t: Omit<Toast, "id">) => void;

export function Boxes({ ov, id, toast }: { ov: Overview; id?: number; toast: ToastFn }) {
  const box = ov.boxes.find((b) => b.id === id) ?? ov.boxes[0];
  if (!box) return <main className="page"><Card title="Boxes"><Empty>No box has reported yet.</Empty></Card></main>;
  return (
    <main className="page">
      <nav className="tabs" aria-label="Boxes">
        {ov.boxes.map((b) => (
          <a key={b.id} href={`#/boxes/${b.id}`} aria-current={b.id === box.id ? "page" : undefined}>
            <span className={`dot st-${b.lost ? "lost" : b.state ?? "unknown"}`} style={{ background: "var(--c)" }} />{b.name}
          </a>
        ))}
      </nav>
      <BoxDetail box={box} tz={ov.site.timezone} toast={toast} />
    </main>
  );
}

function BoxDetail({ box, tz, toast }: { box: Box; tz: string; toast: ToastFn }) {
  const [hours, setHours] = useState(6);
  const [series, setSeries] = useState<Sample[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () => api.series(box.id, hours).then((s) => alive && setSeries(s)).catch(() => undefined);
    load();
    const t = window.setInterval(load, 15000);
    return () => { alive = false; window.clearInterval(t); };
  }, [box.id, hours]);
  const pts = (k: keyof Sample) => series.map((s) => [s.t, s[k] as number | null] as [number, number | null]);
  const w = box.weather;
  return (
    <>
      <section className="card">
        <div className="boxc">
          <div className="boxc-h" style={{ flexWrap: "wrap" }}>
            <h1 className="section-title">{box.name}</h1>
            <StatePill state={box.state} lost={box.lost} />
            {box.levels.filter((l) => l > 0).map((l) => <LevelBadge key={l} level={l} short />)}
            <span className="muted" style={{ marginLeft: "auto" }}>{coord(box.lat, box.lon)} · {box.pos_source === "gps" ? "GPS fix" : "surveyed"} · seen {ago(box.age_s)}</span>
          </div>
          <HealthChips box={box} />
        </div>
      </section>

      <div className="row3">
        <Card title="Detection" sub="what the box measured and decided" id="h-det">
          <dl className="kv-list">
            <dt>Gas score</dt><dd className="mono">{num(box.gas?.score ?? null, 2)} · {box.gas?.class}</dd>
            <dt>Depth bands</dt><dd>
              <div className="stack" style={{ gap: 4 }}>
                {(box.gas?.bands ?? []).map((v, i) => (
                  <div key={i} className="inline" style={{ gap: 8 }}>
                    <span className="note" style={{ width: 34 }}>{["low", "mid", "high"][i]}</span>
                    <div className="meter" style={{ flex: 1 }}><i style={{ width: `${Math.min(100, v * 100)}%`, ["--c" as string]: v > 0.5 ? "var(--ember)" : "var(--forest-2)" }} /></div>
                    <span className="mono note" style={{ width: 36, textAlign: "right" }}>{v.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </dd>
            <dt>Flame vote</dt><dd>{box.flame ? <span className="chip on">Flame seen (5 of 8 reads)</span> : "No flame"}</dd>
            <dt>Camera</dt><dd>{box.camera?.valid ? `${cap(box.camera.label)} · ${num((box.camera.conf ?? 0) * 100, 0)} %` : "Off or rejected frame"}</dd>
            {box.vision && <><dt>Gateway vision</dt><dd>{cap(box.vision.label)} · {num(box.vision.conf * 100, 0)} % · {clock(box.vision.t)}</dd></>}
            <dt>Mode</dt><dd>{cap(box.mode ?? "–")}</dd>
          </dl>
        </Card>
        <Card title="Fire weather" sub="Canadian FWI, computed hourly on the box" id="h-fwi">
          <div className="stack">
            <div className="inline" style={{ alignItems: "baseline" }}>
              <span className="big-num">{num(box.fwi?.value ?? null, 1)}</span>
              <span className="muted">{box.fwi ? cap(box.fwi.danger_name) : "unknown"}{box.fwi?.provisional ? " · provisional" : ""}</span>
            </div>
            <DangerScale fwi={box.fwi} />
            <div className="kv" style={{ gridTemplateColumns: "repeat(5, 1fr)" }}>
              {(["ffmc", "dmc", "dc", "isi", "bui"] as const).map((k) => (
                <div key={k}><div className="k">{k.toUpperCase()}</div><div className="v">{num(w?.codes[k] ?? null, k === "ffmc" || k === "isi" ? 1 : 0)}</div></div>
              ))}
            </div>
          </div>
        </Card>
        <Card title="Weather at the box" sub={box.weather_simulated ? "wind and rain simulated in the prototype" : undefined} id="h-wx">
          <div className="kv" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <div><div className="k">Temperature</div><div className="v">{num(w?.temp_c ?? null, 1)}<small> °C</small></div></div>
            <div><div className="k">Humidity</div><div className="v">{num(w?.rh ?? null, 0)}<small> %</small></div></div>
            <div><div className="k">Wind {box.weather_simulated && <span className="chip sim">sim</span>}</div><div className="v">{w?.wind_kmh ?? "–"}<small> km/h</small></div></div>
            <div><div className="k">Rain 24 h {box.weather_simulated && <span className="chip sim">sim</span>}</div><div className="v">{num(w?.rain_mm ?? null, 1)}<small> mm</small></div></div>
            <div><div className="k">Battery</div><div className="v">{box.battery_pct ?? "–"}<small> %</small></div></div>
            <div><div className="k">LoRa</div><div className="v">{box.rssi ?? "–"}<small> dBm · {num(box.snr, 0)} dB</small></div></div>
          </div>
        </Card>
      </div>

      <Card title="History" sub={`${series.length} samples`} id="h-hist" right={
        <div className="inline" role="group" aria-label="Time range">
          {[1, 6, 24].map((h) => <button key={h} className={`btn sm${h === hours ? " primary" : ""}`} onClick={() => setHours(h)}>{h} h</button>)}
        </div>}>
        <div className="row3">
          <div><div className="note" style={{ marginBottom: 6 }}>Gas score (0 clean air, 1 dense smoke)</div>
            <LineChart label="Gas score history" tz={tz} yMin={0} yMax={1} series={[{ name: "gas", color: "var(--ember)", points: pts("gas") }]} /></div>
          <div><div className="note" style={{ marginBottom: 6 }}>Fire Weather Index over EFFIS classes</div>
            <LineChart label="FWI history" tz={tz} yMin={0} bands={dangerBands()} series={[{ name: "fwi", color: "var(--forest)", points: pts("fwi") }]} /></div>
          <div><div className="note" style={{ marginBottom: 6 }}>Battery % (solid) and RSSI + 150 dBm (dashed)</div>
            <LineChart label="Battery and signal history" tz={tz} yMin={0} yMax={100} series={[
              { name: "battery", color: "var(--teal)", points: pts("battery") },
              { name: "rssi", color: "var(--slate)", dashed: true, points: series.map((s) => [s.t, s.rssi == null ? null : s.rssi + 150]) },
            ]} /></div>
        </div>
      </Card>

      <Commands box={box} toast={toast} />
    </>
  );
}

function Commands({ box, toast }: { box: Box; toast: ToastFn }) {
  const [ask, setAsk] = useState<null | "force_alert" | "reset_fire">(null);
  const [th, setTh] = useState({ smoke_on: 0.4, smoke_off: 0.2, camera: 0.6 });
  const [wx, setWx] = useState({ enable: true, wind: 25, rain: 0 });
  const run = async (p: Promise<{ status: string; error?: string }>, what: string) => {
    try { const r = await p; toast({ tone: r.status === "done" ? "ok" : "info", title: `${what}: ${r.status}`, body: r.status === "queued" ? "sent with the next gateway exchange" : undefined }); }
    catch (e) { toast({ tone: "error", title: `${what} failed`, body: (e as Error).message }); }
  };
  return (
    <Card title="Commands" sub="sent by the gateway to the box at its next transmission (LoRa downlink)" id="h-cmd">
      <div className="row3">
        <div className="stack">
          <div className="note">Quick actions</div>
          <div className="inline">
            <button className="btn" onClick={() => run(api.command("ping", box.id), "Ping")}>Ping</button>
            <button className="btn" onClick={() => setAsk("force_alert")}>Force Alert mode</button>
            <button className="btn danger" onClick={() => setAsk("reset_fire")}>Reset fire state</button>
          </div>
        </div>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); run(api.command("thresholds", box.id, th), "Thresholds"); }}>
          <div className="note">Detection thresholds (0 to 1)</div>
          <div className="form-row">
            {(["smoke_on", "smoke_off", "camera"] as const).map((k) => (
              <div className="field" key={k}>
                <label htmlFor={`th-${k}`}>{k === "smoke_on" ? "Smoke on" : k === "smoke_off" ? "Smoke off" : "Camera"}</label>
                <input id={`th-${k}`} type="number" step="0.01" min="0.01" max="0.99" value={th[k]} onChange={(e) => setTh({ ...th, [k]: +e.target.value })} />
              </div>
            ))}
            <button className="btn primary" type="submit" disabled={!(th.smoke_off < th.smoke_on)}>Send</button>
          </div>
          {!(th.smoke_off < th.smoke_on) && <span className="note" style={{ color: "var(--ember)" }}>Smoke off must stay below smoke on.</span>}
        </form>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); run(api.simWeather(box.id, wx.enable, wx.wind, wx.rain), "Simulated weather"); }}>
          <div className="note">Simulated wind and rain (prototype sensors)</div>
          <div className="form-row">
            <div className="field"><label htmlFor="wx-w">Wind km/h</label><input id="wx-w" type="number" min="0" max="150" value={wx.wind} onChange={(e) => setWx({ ...wx, wind: +e.target.value })} /></div>
            <div className="field"><label htmlFor="wx-r">Rain mm</label><input id="wx-r" type="number" min="0" max="100" step="0.1" value={wx.rain} onChange={(e) => setWx({ ...wx, rain: +e.target.value })} /></div>
            <button className="btn primary" type="submit">Apply</button>
          </div>
        </form>
      </div>
      {ask && (
        <Confirm title={ask === "reset_fire" ? `Reset the fire state of ${box.name}?` : `Force ${box.name} into Alert mode?`}
          tone={ask === "reset_fire" ? "danger" : "primary"} confirm={ask === "reset_fire" ? "Reset" : "Force Alert"}
          body={ask === "reset_fire" ? "Use only after ground teams confirm the fire is out. The box re-raises Fire if its sensors still see one." : "The box scans every 30 s until the gateway or the fire weather releases it."}
          onConfirm={() => run(api.command(ask, box.id), ask === "reset_fire" ? "Reset fire" : "Force Alert")} onClose={() => setAsk(null)} />
      )}
    </Card>
  );
}
