import { useEffect, useState } from "react";
import type { Conn, Toast } from "../lib/live";
import type { Overview } from "../lib/types";
import { LEVEL_LABEL, ago, clock, num } from "../lib/format";
import { BrandMark, IBell, IBellOff, IBoxes, ICog, IDrone, IFlame, IMap, IMoon, IRadio, ISun, IX } from "./Icons";
import { Confirm } from "./ui";

export type Route = "ops" | "network" | "boxes" | "response" | "system";

export function TopBar({ route, ov, conn, theme, setTheme, sound, toggleSound }: {
  route: Route; ov: Overview | null; conn: Conn; theme: string; setTheme: (t: string) => void; sound: boolean; toggleSound: () => void;
}) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now() / 1000), 1000); return () => window.clearInterval(t); }, []);
  const open = ov?.alerts.length ?? 0;
  const links: [Route, string, JSX.Element][] = [
    ["ops", "Operations", <IMap key="m" />], ["network", "Network", <IRadio key="n" />], ["boxes", "Boxes", <IBoxes key="b" />], ["response", "Response", <IDrone key="d" />], ["system", "System", <ICog key="c" />],
  ];
  return (
    <header className="topbar">
      <div className="brand">
        <BrandMark className="brand-mark" />
        <div style={{ minWidth: 0 }}>
          <div className="brand-name">Forest Fire Network</div>
          <div className="brand-site">{ov?.site.name ?? "connecting…"}</div>
        </div>
      </div>
      <nav className="nav" aria-label="Views">
        {links.map(([r, label, icon]) => (
          <a key={r} href={`#/${r === "ops" ? "" : r}`} aria-current={route === r ? "page" : undefined}>
            {icon}<span className="lbl">{label}</span>
            {r === "ops" && open > 0 && <span className="count" aria-label={`${open} active alerts`}>{open}</span>}
          </a>
        ))}
      </nav>
      <div className="topbar-right">
        <span className={`badge ${conn === "live" ? "lv lv-0" : "lv lv-2"}`} title="Live connection to the dashboard backend">
          <span className={`dot${conn === "live" ? " pulse" : ""}`} style={{ ["--c" as string]: conn === "live" ? "var(--ok)" : "var(--amber)" }} />
          {conn === "live" ? "Live" : conn === "connecting" ? "Connecting" : "Reconnecting"}
        </span>
        <span className="clock" aria-label="Site time">{clock(now)}</span>
        <button className="icon-btn" aria-pressed={sound} onClick={toggleSound} title={sound ? "Fire alarm sound on" : "Fire alarm sound off"} aria-label="Fire alarm sound">
          {sound ? <IBell /> : <IBellOff />}
        </button>
        <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "Light theme" : "Dark theme"} title="Theme">
          {theme === "dark" ? <ISun /> : <IMoon />}
        </button>
      </div>
    </header>
  );
}

export function StatusStrip({ ov }: { ov: Overview }) {
  const lv = ov.level.top;
  const f = ov.fusion;
  const last = Math.min(...ov.boxes.map((b) => b.age_s ?? Infinity));
  return (
    <div className="strip" role="region" aria-label="Network status">
      <div className={`level-cell lv-${lv}`}>
        <span className="level-big" aria-hidden="true">{lv ? `L${lv}` : "OK"}</span>
        <div>
          <div className="k">Network level</div>
          <div className="v">{LEVEL_LABEL[lv]}</div>
        </div>
      </div>
      <div>
        <div className="k">Boxes online</div>
        <div className="v"><span className="mono">{ov.counts.online}/{ov.counts.boxes}</span><small>{isFinite(last) ? `last frame ${ago(last)}` : "no frame yet"}</small></div>
      </div>
      <div>
        <div className="k">Fire weather</div>
        <div className="v">{ov.fwi_worst ? <><span>{ov.fwi_worst.danger_name[0].toUpperCase() + ov.fwi_worst.danger_name.slice(1)}</span><small className="mono">FWI {num(ov.fwi_worst.value, 1)}</small></> : <small>unknown</small>}</div>
      </div>
      <div>
        <div className="k">Fire probability</div>
        <div className="v">{f ? <><span className="mono">{(f.posterior * 100).toFixed(1)} %</span><small className="mono">S {f.statistic.toFixed(2)} / 2.94</small></> : <small>no evidence</small>}</div>
      </div>
      <div>
        <div className="k">Gateway link</div>
        <div className="v" style={{ color: ov.link.online ? undefined : "var(--ember)" }}>
          <span>{ov.link.online ? "Online" : "Offline"}</span>
          <small>{ov.link.online ? `${ov.link.mode} · ${ago(ov.link.age_s)}` : ov.link.error || "no data"}</small>
        </div>
      </div>
    </div>
  );
}

export function FireBanner({ ov, onAck }: { ov: Overview; onAck: () => Promise<void> }) {
  const [ask, setAsk] = useState(false);
  const [busy, setBusy] = useState(false);
  const a = ov.unacked_fire;
  if (ov.level.top !== 3 && !a) return null;
  const boxes = ov.fire_boxes.length ? ov.fire_boxes : a ? [a.box] : [];
  const names = boxes.map((id) => ov.boxes.find((b) => b.id === id)?.name ?? `Box ${id}`).join(", ");
  const box = ov.boxes.find((b) => b.id === boxes[0]);
  return (
    <div className={`banner${a ? "" : " acked"}`} role="alert">
      <span className="banner-icon"><IFlame size={20} /></span>
      <div>
        <div className="banner-title">Fire confirmed · {names || "network"}</div>
        <div className="banner-sub">
          {box?.reasons?.length ? `${box.reasons.filter((r) => r !== "fwi").join(" + ")} · ` : ""}
          {box ? `${box.lat.toFixed(5)}, ${box.lon.toFixed(5)} · ` : ""}
          {a ? `raised ${clock(a.t)} · SMS, email and drone mission dispatched` : "acknowledged · waiting for the box to clear"}
        </div>
      </div>
      <span className="spacer" />
      {a && <button className="btn btn-ack" disabled={busy} onClick={() => setAsk(true)}>Acknowledge</button>}
      {ask && (
        <Confirm title="Acknowledge the fire alert?" confirm="Acknowledge" tone="danger"
          body={<>The gateway stops repeating the alert and resets the box once its sensors clear. SMS already sent are not recalled. Confirm only when ground teams have the location.</>}
          onConfirm={async () => { setBusy(true); try { await onAck(); } finally { setBusy(false); } }} onClose={() => setAsk(false)} />
      )}
    </div>
  );
}

export function Toasts({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: number) => void }) {
  return (
    <div className="toasts" aria-live="assertive">
      {toasts.map((t) => (
        <div key={t.id} className={`toast tone-${t.tone}`} role="status">
          <span className="bar" />
          <div><div className="tt">{t.title}</div>{t.body && <div className="tb">{t.body}</div>}</div>
          <button className="btn ghost sm" onClick={() => dismiss(t.id)} aria-label="Dismiss"><IX size={14} /></button>
        </div>
      ))}
    </div>
  );
}
