import { useMemo } from "react";
import { DANGER } from "../lib/format";

export interface Series { name: string; color: string; points: [number, number | null][]; dashed?: boolean }

const fmtTime = (t: number, tz: string) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit" }).format(new Date(t * 1000));

function ticks(lo: number, hi: number, n = 4) {
  const span = hi - lo || 1, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

/** Time-series line chart. `bands` paints horizontal ranges (e.g. EFFIS danger classes) behind the lines. */
export function LineChart({ series, height = 180, yMin, yMax, unit = "", tz = "Africa/Tunis", bands, threshold, label }: {
  series: Series[]; height?: number; yMin?: number; yMax?: number; unit?: string; tz?: string;
  bands?: { lo: number; hi: number; color: string; label?: string }[]; threshold?: { y: number; label: string }; label: string;
}) {
  const W = 640, H = height, L = 44, R = 12, T = 12, B = 24;
  const all = series.flatMap((s) => s.points.filter((p) => p[1] != null)) as [number, number][];
  const geom = useMemo(() => {
    if (!all.length) return null;
    const t0 = Math.min(...all.map((p) => p[0])), t1 = Math.max(...all.map((p) => p[0]));
    let lo = yMin ?? Math.min(...all.map((p) => p[1])), hi = yMax ?? Math.max(...all.map((p) => p[1]));
    if (threshold) { lo = Math.min(lo, threshold.y); hi = Math.max(hi, threshold.y); }
    if (hi - lo < 1e-6) { hi += 1; lo -= 1; }
    if (yMin == null) lo -= (hi - lo) * 0.08;
    if (yMax == null) hi += (hi - lo) * 0.08;
    const x = (t: number) => L + ((t - t0) / Math.max(1, t1 - t0)) * (W - L - R);
    const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    return { t0, t1, lo, hi, x, y };
  }, [all, yMin, yMax, threshold, H]);

  if (!geom) return <div className="empty">No history yet. Points appear as the gateway reports.</div>;
  const { t0, t1, lo, hi, x, y } = geom;
  const xt = [t0, t0 + (t1 - t0) / 2, t1];
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {bands?.map((b, i) => {
        const a = Math.max(lo, b.lo), c = Math.min(hi, b.hi);
        if (c <= a) return null;
        return <rect key={i} x={L} width={W - L - R} y={y(c)} height={y(a) - y(c)} fill={b.color} opacity=".14" />;
      })}
      {ticks(lo, hi).map((v) => (
        <g key={v}>
          <line className="gridl" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
          <text className="tick" x={L - 6} y={y(v) + 3.5} textAnchor="end">{v}{unit}</text>
        </g>
      ))}
      {threshold && (
        <g>
          <line x1={L} x2={W - R} y1={y(threshold.y)} y2={y(threshold.y)} stroke="var(--ember)" strokeDasharray="5 4" strokeWidth="1.3" />
          <text className="lab" x={W - R} y={y(threshold.y) - 5} textAnchor="end" fill="var(--ember)">{threshold.label}</text>
        </g>
      )}
      <line className="axis" x1={L} x2={W - R} y1={H - B} y2={H - B} />
      {xt.map((t, i) => <text key={i} className="tick" x={x(t)} y={H - 7} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>{fmtTime(t, tz)}</text>)}
      {series.map((s) => {
        const pts = s.points.filter((p) => p[1] != null) as [number, number][];
        if (!pts.length) return null;
        const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
        const last = pts[pts.length - 1];
        return (
          <g key={s.name}>
            <path d={d} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeDasharray={s.dashed ? "5 4" : undefined} />
            <circle cx={x(last[0])} cy={y(last[1])} r="3.5" fill={s.color} />
          </g>
        );
      })}
    </svg>
  );
}

export const DANGER_COLORS = ["#3f8f5a", "#7a9a2e", "#d4a21c", "#d4701a", "#b53a1c", "#6e1b1b"];
export const dangerBands = () => DANGER.map((d, i) => ({ lo: d.lo, hi: d.hi, color: DANGER_COLORS[i], label: d.name }));

/** FWI forecast: q10..q90 band and median, per day, over the EFFIS danger classes. */
export function ForecastChart({ days, label }: { days: { day: number; q10: number; q50: number; q90: number; p_high: number }[]; label: string }) {
  const W = 640, H = 210, L = 40, R = 14, T = 16, B = 30;
  const hi = Math.max(55, ...days.map((d) => d.q90 + 4));
  const x = (i: number) => L + (i + 0.5) * ((W - L - R) / Math.max(1, days.length));
  const y = (v: number) => T + (1 - v / hi) * (H - T - B);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {dangerBands().map((b, i) => (
        <rect key={i} x={L} width={W - L - R} y={y(Math.min(hi, b.hi))} height={Math.max(0, y(b.lo) - y(Math.min(hi, b.hi)))} fill={b.color} opacity=".13" />
      ))}
      {[0, 10, 20, 30, 40, 50].filter((v) => v <= hi).map((v) => (
        <text key={v} className="tick" x={L - 6} y={y(v) + 3.5} textAnchor="end">{v}</text>
      ))}
      <line className="axis" x1={L} x2={W - R} y1={H - B} y2={H - B} />
      {days.map((d, i) => (
        <g key={d.day}>
          <rect x={x(i) - 22} width="44" y={y(d.q90)} height={Math.max(2, y(d.q10) - y(d.q90))} rx="6" fill="var(--forest-2)" opacity=".22" />
          <line x1={x(i) - 22} x2={x(i) + 22} y1={y(d.q50)} y2={y(d.q50)} stroke="var(--forest)" strokeWidth="3" strokeLinecap="round" />
          <text className="tick" x={x(i)} y={y(d.q90) - 6} textAnchor="middle" fill="var(--ink)">{d.q50.toFixed(0)}</text>
          <text className="lab" x={x(i)} y={H - 11} textAnchor="middle">{d.day === 1 ? "Tomorrow" : `Day +${d.day}`}</text>
        </g>
      ))}
    </svg>
  );
}

export function Sparkline({ values, color = "var(--forest-2)", w = 120, h = 28 }: { values: (number | null)[]; color?: string; w?: number; h?: number }) {
  const v = values.filter((x): x is number => x != null);
  if (v.length < 2) return <svg width={w} height={h} aria-hidden="true" />;
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const d = v.map((x, i) => `${i ? "L" : "M"}${((i / (v.length - 1)) * (w - 4) + 2).toFixed(1)},${(h - 3 - ((x - lo) / span) * (h - 6)).toFixed(1)}`).join("");
  return <svg width={w} height={h} aria-hidden="true"><path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" /></svg>;
}
