import { useMemo } from "react";
import type { Box, FireGeometry, Mission, Overview } from "../lib/types";
import { Projection, niceScale, type Pt } from "../lib/geo";

const W = 960, H = 560;
const STATE_COLOR: Record<string, string> = { normal: "var(--ok)", suspicion: "var(--amber)", fire: "var(--ember)", unknown: "var(--slate)" };
type XY = [number, number];
interface Ell { cx: number; cy: number; rx: number; ry: number; mins: number }

/** Deterministic random numbers, so the forest looks the same at every refresh. */
function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const circle = (x: number, y: number, r: number) => `M${(x - r).toFixed(1)},${y.toFixed(1)}a${r.toFixed(1)},${r.toFixed(1)} 0 1,0 ${(2 * r).toFixed(1)},0a${r.toFixed(1)},${r.toFixed(1)} 0 1,0 ${(-2 * r).toFixed(1)},0`;

/** Smooth path through points (Catmull-Rom as cubic Béziers). */
function smooth(pts: XY[]) {
  if (pts.length < 2) return "";
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] ?? p2;
    const c1: XY = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: XY = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}
function sample(pts: XY[], step = 8): XY[] {
  const out: XY[] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [a, b] = [pts[i], pts[i + 1]], n = Math.max(1, Math.hypot(b[0] - a[0], b[1] - a[1]) / step);
    for (let k = 0; k < n; k++) out.push([a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n]);
  }
  return out;
}
const inEll = (x: number, y: number, e: Ell, grow = 1) => ((x - e.cx) / (e.rx * grow)) ** 2 + ((y - e.cy) / (e.ry * grow)) ** 2 <= 1;

/** Plan view of the site drawn from GPS positions only: canopy, relief, water, trail, clearings around the equipment.
 *  Works offline (no tiles). During a fire the canopy inside the spread isochrones changes colour and smoke drifts downwind. */
export function SiteMap({ ov, selected, onSelect, compact = false }: { ov: Overview; selected?: number; onSelect?: (id: number) => void; compact?: boolean }) {
  const active = ov.fire_boxes.length > 0 || !!ov.unacked_fire || ov.level.top === 3;
  const fire: FireGeometry = active ? ov.fire ?? {} : { wind_kmh: ov.fire?.wind_kmh, wind_to_deg: ov.fire?.wind_to_deg, wind_direction_simulated: ov.fire?.wind_direction_simulated };
  const mission: Mission | null = active ? ov.mission : null;
  const gw = ov.site.gateway_pos, base = ov.site.drone_base;
  const valid = (p?: Pt | null): p is Pt => !!p && (p.lat !== 0 || p.lon !== 0);
  const boxes = ov.boxes.filter(valid);

  const proj = useMemo(() => {
    const pts: Pt[] = [...boxes];
    if (valid(gw)) pts.push(gw);
    if (valid(base)) pts.push(base);
    if (valid(ov.site.spare_gateway_pos)) pts.push(ov.site.spare_gateway_pos!);
    Object.values(fire.isochrones ?? {}).forEach((i) => pts.push({ lat: i.bbox[0], lon: i.bbox[1] }, { lat: i.bbox[2], lon: i.bbox[3] }));
    return new Projection(pts, W, H, 92, 1100);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boxes.map((b) => `${b.lat},${b.lon}`).join("|"), gw?.lat, gw?.lon, base?.lat, base?.lon, JSON.stringify(fire.isochrones ?? {})]);

  const bxy = boxes.map((b) => proj.xy(b) as XY);
  const gwXY = valid(gw) ? (proj.xy(gw) as XY) : null;
  const baseXY = valid(base) ? (proj.xy(base) as XY) : null;
  const fireBox = boxes.find((b) => ov.fire_boxes.includes(b.id));
  const fireXY = fireBox ? (proj.xy(fireBox) as XY) : null;

  const ells: Ell[] = Object.entries(fire.isochrones ?? {}).map(([m, v]) => {
    const [x0, y0] = proj.xy({ lat: v.bbox[0], lon: v.bbox[1] }), [x1, y1] = proj.xy({ lat: v.bbox[2], lon: v.bbox[3] });
    return { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, rx: Math.max(12, Math.abs(x1 - x0) / 2), ry: Math.max(10, Math.abs(y1 - y0) / 2), mins: +m };
  }).sort((a, b) => a.mins - b.mins);

  // trail: drone base -> gateway -> boxes (access path for the field team); stream across the low ground
  const nearGw = gwXY ? [...bxy].sort((a, b) => Math.hypot(a[0] - gwXY[0], a[1] - gwXY[1]) - Math.hypot(b[0] - gwXY[0], b[1] - gwXY[1])) : bxy;
  const trailPts: XY[] = (bxy.length > 3 ? [baseXY, gwXY, nearGw[0], nearGw[1]] : [baseXY, gwXY, ...[...bxy].sort((a, b) => b[1] - a[1]).reverse()]).filter(Boolean) as XY[];
  const streamPts: XY[] = [[-20, H * 0.9], [W * 0.22, H * 0.8], [W * 0.42, H * 0.93], [W * 0.62, H * 0.84], [W * 0.82, H * 0.95], [W + 20, H * 0.86]];

  const forest = useMemo(() => {
    const r = rng(20261117);
    const clear: { p: XY; r: number }[] = [...bxy.map((p) => ({ p, r: 34 })), ...(gwXY ? [{ p: gwXY, r: 42 }] : []), ...(baseXY ? [{ p: baseXY, r: 46 }] : [])];
    const trail = sample(trailPts, 6), stream = sample(streamPts, 8);
    const groups = { shadow: "", c0: "", c1: "", c2: "", c3: "", hi: "", burnt: "", scorch: "", ember: "" };
    const step = compact ? 19 : 14.5;
    for (let y = -6; y < H + 12; y += step) {
      for (let x = -6; x < W + 12; x += step) {
        const tx = x + (r() - 0.5) * step * 0.9, ty = y + (r() - 0.5) * step * 0.9;
        const rad = step * (0.34 + r() * 0.24);
        if (clear.some((c) => Math.hypot(tx - c.p[0], ty - c.p[1]) < c.r + rad * 0.4)) continue;
        if (trail.some((p) => Math.hypot(tx - p[0], ty - p[1]) < 7 + rad * 0.5)) continue;
        if (stream.some((p) => Math.hypot(tx - p[0], ty - p[1]) < 9 + rad * 0.5)) continue;
        if (Math.sin(tx * 0.013) * Math.cos(ty * 0.017) > 0.82 && r() < 0.8) continue;   // natural glades
        groups.shadow += circle(tx + rad * 0.3, ty + rad * 0.35, rad);
        const e15 = ells[0], e30 = ells[1];
        if (e15 && inEll(tx, ty, e15)) groups[r() < 0.25 ? "ember" : "burnt"] += circle(tx, ty, rad * 0.9);
        else if (e30 && inEll(tx, ty, e30)) groups[r() < 0.5 ? "scorch" : "c3"] += circle(tx, ty, rad);
        else {
          const k = r();
          groups[k < 0.3 ? "c0" : k < 0.65 ? "c1" : k < 0.9 ? "c2" : "c3"] += circle(tx, ty, rad);
          groups.hi += circle(tx - rad * 0.3, ty - rad * 0.32, rad * 0.36);
        }
      }
    }
    return { groups, trailD: smooth(trailPts), streamD: smooth(streamPts) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proj, compact, JSON.stringify(ells)]);

  const scaleM = niceScale(proj.metres(150));
  const windTo = fire.wind_to_deg ?? null;
  const wv: XY = windTo == null ? [0.5, -0.86] : [Math.sin((windTo * Math.PI) / 180), -Math.cos((windTo * Math.PI) / 180)];

  return (
    <div className="map-wrap">
      <svg className="map forest" viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`Forest site with ${boxes.length} sensor boxes and the gateway${fireBox ? `; fire at ${fireBox.name}` : ""}`}>
        <defs>
          <radialGradient id="ridge" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="var(--relief-hi)" stopOpacity=".9" /><stop offset="1" stopColor="var(--relief-hi)" stopOpacity="0" /></radialGradient>
          <radialGradient id="valley" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="var(--relief-lo)" stopOpacity=".7" /><stop offset="1" stopColor="var(--relief-lo)" stopOpacity="0" /></radialGradient>
          <radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#ffb347" stopOpacity=".95" /><stop offset=".35" stopColor="#ff6a1f" stopOpacity=".55" /><stop offset="1" stopColor="#ff6a1f" stopOpacity="0" /></radialGradient>
          <filter id="smoke" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9" /></filter>
          <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.2" /></filter>
          <filter id="lift" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="1.5" stdDeviation="1.6" floodColor="#0b1a12" floodOpacity=".35" /></filter>
          <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--map-ink)" /></marker>
        </defs>

        {/* ground and relief */}
        <rect width={W} height={H} fill="var(--terrain)" />
        <ellipse cx={W * 0.72} cy={H * 0.24} rx={W * 0.42} ry={H * 0.38} fill="url(#ridge)" />
        <ellipse cx={W * 0.2} cy={H * 0.3} rx={W * 0.3} ry={H * 0.3} fill="url(#ridge)" />
        <ellipse cx={W * 0.45} cy={H * 0.9} rx={W * 0.55} ry={H * 0.3} fill="url(#valley)" />
        <g fill="none" stroke="var(--contour)" strokeWidth="1">
          {[0, 1, 2, 3, 4].map((i) => <ellipse key={i} cx={W * 0.72} cy={H * 0.24} rx={60 + i * 62} ry={38 + i * 40} transform={`rotate(-12 ${W * 0.72} ${H * 0.24})`} />)}
          {[0, 1, 2].map((i) => <ellipse key={`b${i}`} cx={W * 0.2} cy={H * 0.3} rx={50 + i * 55} ry={34 + i * 38} transform={`rotate(18 ${W * 0.2} ${H * 0.3})`} />)}
        </g>

        {/* water and trail under the canopy edge */}
        <path d={forest.streamD} fill="none" stroke="var(--water-bank)" strokeWidth="11" strokeLinecap="round" />
        <path d={forest.streamD} fill="none" stroke="var(--water)" strokeWidth="5" strokeLinecap="round" />
        <path d={forest.trailD} fill="none" stroke="var(--trail-edge)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <path d={forest.trailD} fill="none" stroke="var(--trail)" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="1 7" />

        {/* canopy: one path per colour, thousands of crowns for a handful of DOM nodes */}
        <path d={forest.groups.shadow} fill="var(--canopy-shadow)" opacity=".45" filter="url(#soft)" />
        <path d={forest.groups.c0} fill="var(--canopy-0)" />
        <path d={forest.groups.c1} fill="var(--canopy-1)" />
        <path d={forest.groups.c2} fill="var(--canopy-2)" />
        <path d={forest.groups.hi} fill="var(--canopy-hi)" opacity=".55" />
        <path d={forest.groups.c3} fill="var(--canopy-3)" />
        <path d={forest.groups.scorch} fill="#b8743a" />
        <path d={forest.groups.burnt} fill="#3b2a24" />
        <path d={forest.groups.ember} fill="#e0622a" />

        {/* fire: glow, spread isochrones, smoke downwind */}
        {fireXY && <circle cx={fireXY[0]} cy={fireXY[1]} r="70" fill="url(#glow)" className="fire-glow" />}
        {fireXY && (
          <g className="smoke" filter="url(#smoke)" aria-hidden="true">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <ellipse key={i} className={`puff p${i}`} cx={fireXY[0] + wv[0] * (18 + i * 34)} cy={fireXY[1] + wv[1] * (18 + i * 34) - i * 4}
                       rx={16 + i * 9} ry={11 + i * 6} fill="var(--smoke)" opacity={0.6 - i * 0.08} />
            ))}
          </g>
        )}
        {ells[2] && <ellipse cx={ells[2].cx} cy={ells[2].cy} rx={ells[2].rx} ry={ells[2].ry} fill="var(--ember)" opacity=".1" />}
        {ells[1] && <ellipse cx={ells[1].cx} cy={ells[1].cy} rx={ells[1].rx} ry={ells[1].ry} fill="var(--ember)" opacity=".1" />}
        {ells.map((e) => (
          <g key={e.mins}>
            <ellipse cx={e.cx} cy={e.cy} rx={e.rx} ry={e.ry} fill="none" stroke="var(--ember)" strokeWidth={e.mins === 15 ? 2.2 : 1.6} strokeDasharray={e.mins === 15 ? undefined : "7 5"} />
            <Chip x={e.cx + e.rx * 0.71} y={e.cy - e.ry * 0.71} text={`${e.mins} min`} tone="ember" />
          </g>
        ))}

        {/* LoRa links: direct to the gateway, or to the nearest direct neighbour when relayed; dash flow on recent frames */}
        {boxes.map((b, i) => {
          const [x, y] = bxy[i];
          const recent = b.online && (b.age_s ?? 999) < 30;
          let to: XY | null = gwXY, stroke = linkTone(b);
          if (b.relayed) {
            const cand = boxes.map((o, j) => ({ o, p: bxy[j] })).filter(({ o }) => !o.relayed && o.id !== b.id)
              .sort((p, q) => Math.hypot(p.p[0] - x, p.p[1] - y) - Math.hypot(q.p[0] - x, q.p[1] - y))[0];
            to = cand ? cand.p : gwXY; stroke = "var(--teal)";
          }
          return to ? <line key={`l${b.id}`} className={recent ? "flow" : undefined} x1={x} y1={y} x2={to[0]} y2={to[1]} stroke={stroke} strokeWidth="2.2" strokeDasharray="3 6" strokeLinecap="round" opacity={b.online ? 1 : 0.4} /> : null;
        })}

        {/* drone mission (simulated) */}
        {mission && baseXY && (() => {
          const [tx, ty] = proj.xy(mission.target);
          const mx = (baseXY[0] + tx) / 2, my = Math.min(baseXY[1], ty) - 80;
          return (
            <g>
              <path d={`M${baseXY[0]},${baseXY[1]} Q${mx},${my} ${tx},${ty - 16}`} fill="none" stroke="var(--map-ink)" strokeWidth="1.8" strokeDasharray="8 6" markerEnd="url(#arr)" />
              <g transform={`translate(${mx},${my + 40})`} filter="url(#lift)">
                <circle r="13" fill="var(--surface)" />
                <path d="M-8-5h6M2-5h6M-5-5v3M5-5v3M-4 1h8l-2 4h-4z" stroke="var(--map-ink)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
              </g>
              <Chip x={mx + 18} y={my + 40} text="Drone mission · simulated flight" anchor="start" />
            </g>
          );
        })()}

        {/* source estimate */}
        {fire.source && fire.source.used_as_ignition && (() => {
          const [x, y] = proj.xy(fire.source);
          return (
            <g>
              <circle cx={x} cy={y} r="12" fill="none" stroke="var(--map-ink)" strokeWidth="1.6" />
              <path d={`M${x - 18},${y}H${x - 6}M${x + 6},${y}H${x + 18}M${x},${y - 18}V${y - 6}M${x},${y + 6}V${y + 18}`} stroke="var(--map-ink)" strokeWidth="1.6" />
              <Chip x={x + 22} y={y + 22} anchor="start" text={`Source estimate${fire.source.used_as_ignition ? "" : ` · indicative, ${fire.source.n_boxes_detecting} boxes`}`} />
            </g>
          );
        })()}

        {/* drone base */}
        {baseXY && (
          <g transform={`translate(${baseXY[0]},${baseXY[1]})`} filter="url(#lift)">
            <circle r="17" fill="var(--pad)" stroke="var(--surface)" strokeWidth="3" />
            <text y="5" textAnchor="middle" fontSize="14" fontWeight="800" fill="var(--surface)">H</text>
            <Chip x={22} y={0} anchor="start" text="Drone base" />
          </g>
        )}

        {valid(ov.site.spare_gateway_pos) && (() => {
          const [x, y] = proj.xy(ov.site.spare_gateway_pos!);
          return (
            <g transform={`translate(${x},${y})`}>
              <rect x="-13" y="-13" width="26" height="26" rx="6" fill="var(--surface)" stroke="var(--slate)" strokeWidth="2" strokeDasharray="4 3" />
              <Chip x={20} y={0} anchor="start" text="Spare gateway · standby" muted />
            </g>
          );
        })()}

        {/* gateway mast */}
        {gwXY && (
          <g transform={`translate(${gwXY[0]},${gwXY[1]})`}>
            <g filter="url(#lift)">
              <rect x="-15" y="-15" width="30" height="30" rx="7" fill="var(--surface)" stroke="var(--forest)" strokeWidth="2.2" />
              <path d="M0 9V-6M-6-1a8 8 0 0 1 12 0M-9-5a12 12 0 0 1 18 0M-5 9h10" stroke="var(--forest)" strokeWidth="1.8" fill="none" strokeLinecap="round" />
            </g>
            <Chip x={22} y={-8} anchor="start" text="Gateway" strong />
            <Chip x={22} y={12} anchor="start" text={ov.link.online ? `online · ${ov.link.mode}` : "link offline"} tone={ov.link.online ? undefined : "ember"} />
          </g>
        )}

        {/* boxes */}
        {boxes.map((b, i) => {
          const [x, y] = bxy[i];
          const st = b.lost ? "unknown" : b.state ?? "unknown";
          const c = STATE_COLOR[st];
          const sel = selected === b.id;
          return (
            <g key={b.id} className="box-node" transform={`translate(${x},${y})`} tabIndex={0} role="button"
               aria-label={`${b.name}: ${b.lost ? "lost" : st}. Open details`}
               onClick={() => onSelect?.(b.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect?.(b.id); } }}>
              {(st === "fire" || st === "suspicion") && <circle className="halo" r="18" fill={c} />}
              <g filter="url(#lift)">
                <circle className="ring" r={sel ? 18 : 15} fill="var(--surface)" stroke={c} strokeWidth={sel ? 3.5 : 3} strokeDasharray={b.lost ? "3 3" : undefined} />
                <rect x="-6" y="-6" width="12" height="12" rx="2.5" fill={c} />
                <path d="M-8-8 8-11" stroke="var(--map-ink)" strokeWidth="2.2" strokeLinecap="round" />
              </g>
              {st === "fire" && <Flame />}
              <Chip x={24} y={-9} anchor="start" text={boxes.length > 3 ? b.name.split(",")[0] : b.name} strong />
              <Chip x={24} y={11} anchor="start" tone={st === "fire" ? "ember" : st === "suspicion" ? "amber" : undefined}
                    text={`${b.lost ? "Lost" : st === "unknown" ? "No data" : st[0].toUpperCase() + st.slice(1)}${b.reasons?.filter((r) => r !== "fwi").length ? ` · ${b.reasons.filter((r) => r !== "fwi").join(" + ")}` : ""}`} />
            </g>
          );
        })}

        {/* north, wind, scale */}
        <g transform="translate(58,60)">
          <circle r="32" fill="var(--surface)" opacity=".92" stroke="var(--line-strong)" />
          <path d="M0-27 4-18h-8z" fill="var(--map-ink)" />
          <text y="-34" textAnchor="middle" fontSize="11" fontWeight="800" fill="var(--map-ink)" className="halo-text">N</text>
          {windTo != null && <g transform={`rotate(${windTo})`}><path d="M0 18V-16M-7-8 0-18 7-8" fill="none" stroke="var(--teal)" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" /></g>}
        </g>
        <Chip x={58} y={110} text={fire.wind_kmh != null ? `Wind ${Math.round(fire.wind_kmh)} km/h` : "Wind"} />
        {fire.wind_direction_simulated !== false && <Chip x={58} y={130} text="direction simulated" muted />}
        <g transform={`translate(${W - 24 - proj.px(scaleM)},${H - 24})`}>
          <rect x="-8" y="-24" width={proj.px(scaleM) + 16} height="36" rx="6" fill="var(--surface)" opacity=".88" />
          <path d={`M0 0V6H${proj.px(scaleM)}V0`} fill="none" stroke="var(--map-ink)" strokeWidth="1.6" />
          <text x={proj.px(scaleM) / 2} y="-8" textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--map-ink)">{scaleM >= 1000 ? `${scaleM / 1000} km` : `${scaleM} m`}</text>
        </g>
      </svg>
      <div className="map-legend" aria-hidden="true">
        <span><i className="sw" style={{ background: "var(--canopy-1)" }} />Forest</span>
        <span><i className="sw" style={{ background: "#3b2a24" }} />Burning within 15 min</span>
        <span><i className="sw" style={{ background: "#b8743a" }} />Within 30 min</span>
        <span><svg width="22" height="10"><ellipse cx="11" cy="5" rx="10" ry="4" fill="none" stroke="var(--ember)" strokeDasharray="4 3" /></svg>60 min front</span>
        <span><svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--ok)" strokeWidth="2" strokeDasharray="3 4" /></svg>LoRa</span>
        <span><svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--trail)" strokeWidth="3" strokeDasharray="1 5" strokeLinecap="round" /></svg>Trail</span>
      </div>
    </div>
  );
}

function linkTone(b: Box) {
  if (!b.online) return "var(--slate)";
  const r = b.rssi ?? -90;
  return r >= -105 ? "var(--ok)" : r >= -115 ? "var(--amber)" : "var(--ember)";
}

function Flame() {
  return (
    <g transform="translate(-1,-30)" className="flame">
      <path d="M0 14C-7 9-6 0 0-9c1 6 7 8 6 15-.5 5-3 8-6 8z" fill="#ff6a1f" />
      <path d="M0 14c-3-3-3-7 0-11 3 4 3 8 0 11z" fill="#ffd166" />
    </g>
  );
}

/** Label with its own background, readable over the canopy at any zoom. */
function Chip({ x, y, text, anchor = "middle", strong, tone, muted }: { x: number; y: number; text: string; anchor?: "start" | "middle"; strong?: boolean; tone?: "ember" | "amber"; muted?: boolean }) {
  const fs = strong ? 12.5 : 11.5, w = text.length * fs * 0.56 + 12, h = fs + 8;
  const x0 = anchor === "start" ? x : x - w / 2;
  const fill = tone === "ember" ? "var(--ember)" : tone === "amber" ? "var(--amber)" : "var(--surface)";
  const ink = tone ? "#fff" : muted ? "var(--muted)" : "var(--ink)";
  return (
    <g pointerEvents="none">
      <rect x={x0} y={y - h / 2} width={w} height={h} rx={h / 2} fill={fill} opacity={tone ? 0.95 : 0.9} />
      <text x={x0 + w / 2} y={y + fs * 0.36} textAnchor="middle" fontSize={fs} fontWeight={strong ? 700 : 600} fontStyle={muted ? "italic" : undefined} fill={ink}>{text}</text>
    </g>
  );
}

export function boxColor(b: Box) {
  return STATE_COLOR[b.lost ? "unknown" : b.state ?? "unknown"];
}
