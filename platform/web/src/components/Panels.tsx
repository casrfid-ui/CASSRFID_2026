import { useEffect, useRef, useState } from "react";
import type { ActiveAlert, Box, Fusion, FwiReading, Level, Overview, TimelineEvent } from "../lib/types";
import { DANGER, KIND_LABEL, LEVEL_LABEL, ago, clock, coord, humanReason, num } from "../lib/format";
import { Card, Empty, LevelBadge } from "./ui";
import { ICheck } from "./Icons";
import { DANGER_COLORS } from "./Charts";

export function AlertsPanel({ alerts: raw, boxes }: { alerts: ActiveAlert[]; boxes: Box[] }) {
  const name = (id: number) => (id ? boxes.find((b) => b.id === id)?.name ?? `Box ${id}` : "Network");
  // high fire weather is usually network-wide: one row instead of one per box
  const l1 = raw.filter((a) => a.level === 1);
  const alerts: (ActiveAlert & { label?: string })[] = l1.length > 2
    ? [...raw.filter((a) => a.level !== 1), { ...l1[0], label: `${l1.length} boxes`, reason: l1[0].reason }]
    : raw;
  return (
    <Card title="Active alerts" sub={alerts.length ? `${alerts.length} open` : undefined} flush id="h-alerts">
      {alerts.length === 0 ? (
        <Empty icon={<ICheck />}>No active alert. Every box reports Normal.</Empty>
      ) : (
        <ul className="alist" aria-live="polite">
          {alerts.map((a, i) => (
            <li key={`${a.level}-${a.box}-${i}`}>
              <LevelBadge level={a.level} short strong={a.level === 3} />
              <div>
                <div className="t">{"label" in a && a.label ? a.label : name(a.box)}</div>
                <div className="d">{humanReason(a.reason)}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const KIND_LEVEL: Record<string, string> = { drone: "var(--ink-2)", sms: "var(--teal)", operator: "var(--forest-2)", vision: "var(--teal)" };

export function Timeline({ events, boxes, limit = 60, title = "Action timeline" }: { events: TimelineEvent[]; boxes: Box[]; limit?: number; title?: string }) {
  const seen = useRef<Set<number>>(new Set());
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  useEffect(() => {
    const n = new Set<number>();
    if (seen.current.size) events.forEach((e) => { if (!seen.current.has(e.id)) n.add(e.id); });
    events.forEach((e) => seen.current.add(e.id));
    if (n.size) setFresh(n);
  }, [events]);
  const name = (id: number) => (id ? boxes.find((b) => b.id === id)?.name ?? `Box ${id}` : "");
  const shown = events.filter((e) => e.kind !== "cmd" || e.level > 0).slice(0, limit);
  return (
    <Card title={title} sub="every automatic action, newest first" flush id="h-tl">
      {shown.length === 0 ? <Empty>Nothing yet.</Empty> : (
        <ol className="tl">
          {shown.map((e) => {
            const c = e.kind === "cleared" ? "var(--ok)" : e.kind === "alert" && e.level ? levelColor(e.level as Level) : KIND_LEVEL[e.kind];
            return (
              <li key={e.id} className={fresh.has(e.id) ? "new" : undefined}>
                <span className="when">{clock(e.t)}</span>
                <span className="rail"><i style={{ ["--c" as string]: c }} /></span>
                <span className="what"><b>{KIND_LABEL[e.kind] ?? e.kind}</b>{e.box ? ` · ${name(e.box)}` : ""} · {describe(e)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

const tidy = (t: string) => t.replace(/^L\d [a-z ]+: /i, "").replace(/\s+/g, " ");
const LVN: Record<number, string> = { 1: "High fire weather", 2: "Suspicion", 3: "Fire confirmed", 4: "Box lost", 5: "Maintenance" };
function describe(e: TimelineEvent): string {
  const d = e.data as Record<string, unknown>;
  if (e.kind === "alert" && typeof d.reason === "string") return `${LVN[e.level] ?? ""}: ${humanReason(d.reason)}`;
  if (e.kind === "cleared") return `${LVN[e.level] ?? "Alert"} cleared`;
  if (e.kind === "sms" && typeof d.number === "string") return `fire alert sent to ${d.number}`;
  if (e.kind === "drone" && d.mission && typeof d.mission === "object") {
    const m = d.mission as { id: string; target: { lat: number; lon: number } };
    return `mission ${m.id} ready, target ${coord(m.target.lat, m.target.lon)} · simulated flight`;
  }
  if (e.kind === "vision" && typeof d.label === "string") return `gateway check of the photo: ${d.label} ${Math.round(Number(d.conf) * 100)} %`;
  return tidy(e.text);
}
export const levelColor = (l: Level) => ["var(--ok)", "var(--ochre)", "var(--amber)", "var(--ember)", "var(--slate)", "var(--teal)"][l];

export function DangerScale({ fwi }: { fwi: FwiReading | null | undefined }) {
  const v = fwi?.value ?? null;
  const pos = v == null ? null : Math.min(99.5, (() => {
    const i = DANGER.findIndex((d) => v < d.hi);
    const k = i < 0 ? 5 : i, d = DANGER[k];
    return ((k + Math.min(1, (v - d.lo) / (d.hi - d.lo))) / 6) * 100;
  })());
  return (
    <div>
      <div className="danger-scale" role="img" aria-label={v == null ? "Fire weather unknown" : `Fire Weather Index ${v.toFixed(1)}, ${fwi?.danger_name}`}>
        {DANGER_COLORS.map((c, i) => <div key={i} className="seg" style={{ background: c }} />)}
        {pos != null && <span className="marker" style={{ left: `${pos}%` }} />}
      </div>
      <div className="danger-names">
        {DANGER.map((d, i) => <span key={d.name} className={fwi?.danger === i ? "cur" : undefined}>{d.name}</span>)}
      </div>
    </div>
  );
}

/** Sequential evidence (SPRT) as the operator should read it: where the score is, and who pushed it there. */
export function EvidencePanel({ fusion, boxes }: { fusion: Fusion | null; boxes: Box[] }) {
  if (!fusion) return <Card title="Evidence fusion" id="h-ev"><Empty>No evidence yet.</Empty></Card>;
  const A = 2.944, span = 10;
  const pct = (s: number) => Math.max(2, Math.min(98, 50 + (s / span) * 50));
  const name = (id: number) => boxes.find((b) => b.id === id)?.name.split(",")[0] ?? `Box ${id}`;
  const all = [...fusion.contributions].sort((a, b) => Math.abs(b.llr) - Math.abs(a.llr));
  const rows = all.slice(0, 6);
  const max = Math.max(4, ...all.map((r) => Math.abs(r.llr)));
  const tone = fusion.confirmed ? "var(--ember)" : fusion.suspected ? "var(--amber)" : "var(--ok)";
  return (
    <Card title="Evidence fusion" sub="sequential test across boxes, prior from fire weather" id="h-ev"
          right={<span className={`badge lv ${fusion.confirmed ? "lv-3 strong" : fusion.suspected ? "lv-2" : "lv-0"}`}>
            {fusion.confirmed ? "Fire confirmed" : fusion.suspected ? "Suspected" : "Below threshold"}</span>}>
      <div className="stack">
        <div>
          <div className="inline" style={{ justifyContent: "space-between", fontSize: 12, color: "var(--muted)" }}>
            <span>Score S = <b className="mono" style={{ color: "var(--ink)" }}>{fusion.statistic.toFixed(2)}</b></span>
            <span>Posterior <b className="mono" style={{ color: "var(--ink)" }}>{(fusion.posterior * 100).toFixed(1)} %</b></span>
            <span>Confirm at S ≥ <b className="mono">2.94</b></span>
          </div>
          <div className="sprt" style={{ marginTop: 8 }}>
            <span className="thr" style={{ left: `${pct(A)}%` }} />
            <span className="needle" style={{ left: `${pct(fusion.statistic)}%`, ["--c" as string]: tone }} />
          </div>
          <div className="inline" style={{ justifyContent: "space-between", fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
            <span>no fire</span><span>prior {(fusion.prior * 100).toFixed(1)} %</span><span>fire</span>
          </div>
        </div>
        <div className="evidence" aria-label="Contribution of each witness">
          {rows.length === 0 && <span className="note">No witness is active: the score sits at the fire-weather prior.</span>}
          {all.length > rows.length && <span className="note" style={{ order: 99 }}>+ {all.length - rows.length} weaker witnesses</span>}
          {rows.map((r, i) => {
            const w = (Math.abs(r.llr) / max) * 50;
            return (
              <div className="ev-row" key={i}>
                <span>{name(r.box)} · {r.witness}</span>
                <span className="ev-bar"><span className="mid" />
                  <i style={{ left: r.llr >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`, background: r.llr >= 0 ? "var(--ember)" : "var(--forest-2)" }} /></span>
                <span className="mono r" style={{ textAlign: "right" }}>{r.llr >= 0 ? "+" : ""}{r.llr.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

export function LinkLine({ ov }: { ov: Overview }) {
  const l = ov.link;
  return <span>{l.online ? `Gateway ${l.mode === "pull" ? "polled" : "pushing"} · ${ago(l.age_s)}` : `Gateway offline · ${l.error || "no data"}`}</span>;
}

export { LEVEL_LABEL, num };
