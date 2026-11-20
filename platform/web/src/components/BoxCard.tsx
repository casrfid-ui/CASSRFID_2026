import type { Box } from "../lib/types";
import { ago, cap, num } from "../lib/format";
import { StatePill } from "./ui";
import { Sparkline } from "./Charts";
import { IBattery, ISignal } from "./Icons";

const HEALTH_LABEL: Record<string, string> = { gas: "Gas", flame: "Flame", camera: "Camera", battery: "Battery", housing: "Housing", supply: "Supply", link: "Link" };

export function HealthChips({ box }: { box: Box }) {
  return (
    <div className="health" aria-label="Sensor and power health">
      {Object.entries(box.health).map(([k, v]) => {
        const bad = v === "fault" || v === "down" || v === "hot";
        const warn = v === "low" || v === "weak" || v === "unknown";
        return (
          <span key={k} className={`hc${bad ? " bad" : warn ? " warn" : ""}`}>
            <span className="dot" style={{ background: bad ? "var(--ember)" : warn ? "var(--amber)" : "var(--ok)" }} />
            {HEALTH_LABEL[k]}{v !== "ok" ? `: ${v}` : ""}
          </span>
        );
      })}
    </div>
  );
}

export function BoxCard({ box, gasHistory }: { box: Box; gasHistory?: (number | null)[] }) {
  const g = box.gas;
  return (
    <article className="card">
      <div className="boxc">
        <div className="boxc-h">
          <a href={`#/boxes/${box.id}`}><h3>{box.name}</h3></a>
          <StatePill state={box.state} lost={box.lost} />
          <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>{box.online ? `seen ${ago(box.age_s)}` : box.lost ? "no frames" : "waiting"}</span>
        </div>
        {box.reasons && box.reasons.length > 0 && (
          <div className="inline" aria-label="Reasons reported by the box">
            {["gas", "flame", "camera", "fwi"].map((r) => (
              <span key={r} className={`chip${box.reasons!.includes(r) ? " on" : ""}`}>{r === "fwi" ? "FWI" : cap(r)}</span>
            ))}
          </div>
        )}
        <div className="kv">
          <div>
            <div className="k">Gas score</div>
            <div className="v">{num(g?.score ?? null, 2)} <small>{g?.class}</small></div>
            {gasHistory && <Sparkline values={gasHistory} color={box.state === "fire" ? "var(--ember)" : "var(--forest-2)"} w={110} h={22} />}
          </div>
          <div>
            <div className="k">Fire weather</div>
            <div className="v">{num(box.fwi?.value ?? null, 1)} <small>{box.fwi?.danger_name}</small></div>
          </div>
          <div>
            <div className="k inline" style={{ gap: 4 }}><IBattery size={13} /> Battery</div>
            <div className="v" style={{ color: (box.battery_pct ?? 100) < 20 ? "var(--ember)" : undefined }}>{box.battery_pct ?? "–"}<small> %</small></div>
          </div>
          <div>
            <div className="k inline" style={{ gap: 4 }}><ISignal size={13} /> LoRa link</div>
            <div className="v">{box.rssi ?? "–"}<small> dBm · {num(box.snr, 0)} dB</small></div>
          </div>
        </div>
        <HealthChips box={box} />
        <div className="note">
          Mode {box.mode ?? "–"} · {box.pos_source === "gps" ? "GPS position" : "surveyed position"}
          {box.weather_simulated ? " · wind and rain simulated" : ""}
        </div>
      </div>
    </article>
  );
}

const ORDER: Record<string, number> = { fire: 0, suspicion: 1, lost: 2, unknown: 3, normal: 4 };
export const sortBoxes = (bs: Box[]) => [...bs].sort((a, b) => (ORDER[a.lost ? "lost" : a.state ?? "unknown"] - ORDER[b.lost ? "lost" : b.state ?? "unknown"]) || a.id - b.id);

/** Compact tile for networks with many boxes: the worst states come first. */
export function BoxTile({ box, gasHistory }: { box: Box; gasHistory?: (number | null)[] }) {
  const st = box.lost ? "lost" : box.state ?? "unknown";
  const issues = Object.entries(box.health).filter(([, v]) => v !== "ok" && v !== "unknown").map(([k, v]) => `${k} ${v}`);
  return (
    <a className={`tile st-${st}`} href={`#/boxes/${box.id}`} aria-label={`${box.name}, ${st}`}>
      <div className="tile-h">
        <b>{box.name}</b>
        <StatePill state={box.state} lost={box.lost} />
      </div>
      <div className="tile-m">
        <span>Gas<b style={{ color: box.state === "fire" ? "var(--ember)" : undefined }}>{num(box.gas?.score ?? null, 2)}</b></span>
        <span>Battery<b style={{ color: (box.battery_pct ?? 100) < 20 ? "var(--ember)" : undefined }}>{box.battery_pct ?? "–"}%</b></span>
        <span>RSSI<b>{box.rssi ?? "–"}</b></span>
      </div>
      {gasHistory && <Sparkline values={gasHistory} color={box.state === "fire" ? "var(--ember)" : box.state === "suspicion" ? "var(--amber)" : "var(--forest-2)"} w={220} h={22} />}
      <div className="tile-f">
        {box.reasons?.filter((r) => r !== "fwi").map((r) => <span key={r} className="chip on">{cap(r)}</span>)}
        {box.relayed && <span className="chip">relayed</span>}
        {issues.length > 0 && <span className="chip" style={{ color: "var(--amber)" }}>{issues.join(", ")}</span>}
        <span style={{ marginLeft: "auto" }}>{box.lost ? "no frame" : ago(box.age_s)}</span>
      </div>
    </a>
  );
}
