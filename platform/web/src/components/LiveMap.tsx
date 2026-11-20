import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { AppConfig, Box, Overview, TileSource } from "../lib/types";
import { SiteMap } from "./SiteMap";

const DEFAULT_TILES: TileSource[] = [
  { id: "osm", name: "OpenStreetMap", url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' },
  { id: "topo", name: "Terrain", url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", max_zoom: 17, subdomains: "abc",
    attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM &middot; style &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)' },
];
const OFFLINE = "offline";
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const valid = (p?: { lat: number; lon: number } | null) => !!p && (p.lat !== 0 || p.lon !== 0);
const ll = (p: { lat: number; lon: number }): L.LatLngTuple => [p.lat, p.lon];
const metres = (a: L.LatLngTuple, b: L.LatLngTuple) => L.latLng(a).distanceTo(L.latLng(b));
function offset(p: L.LatLngTuple, m: number, deg: number): L.LatLngTuple {
  const t = (deg * Math.PI) / 180;
  return [p[0] + (m * Math.cos(t)) / 110540, p[1] + (m * Math.sin(t)) / (111320 * Math.cos((p[0] * Math.PI) / 180))];
}
function stateOf(b: Box) { return b.lost ? "lost" : b.state ?? "unknown"; }
function quality(b: Box) {
  if (!b.online) return "down";
  const r = b.rssi ?? -150;
  return r >= -100 ? "good" : r >= -112 ? "fair" : "weak";
}
function readMode(fallback: string) { try { return localStorage.getItem("ffn.map") || fallback; } catch { return fallback; } }

/** Live network on a real base map (OpenStreetMap or OpenTopoMap tiles), with an offline illustrated map as fallback:
 *  in the forest the operator may have no internet, and the map must still work. */
export function LiveMap({ ov, config, onSelect, height = 560 }: { ov: Overview; config: AppConfig | null; onSelect?: (id: number) => void; height?: number }) {
  const tiles = config?.map_tiles?.length ? config.map_tiles : DEFAULT_TILES;
  const [mode, setModeState] = useState(() => readMode(tiles[0].id));
  const [notice, setNotice] = useState("");
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const base = useRef<L.TileLayer | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const fitted = useRef(false);
  const onSel = useRef(onSelect);
  onSel.current = onSelect;
  const setMode = (m: string) => { setModeState(m); setNotice(""); try { localStorage.setItem("ffn.map", m); } catch { /* ignore */ } };
  const online = mode !== OFFLINE;

  // create / destroy the Leaflet map
  useEffect(() => {
    if (!online || !host.current) return;
    const m = L.map(host.current, { zoomControl: false, attributionControl: true, preferCanvas: false, zoomSnap: 0.25 });
    L.control.zoom({ position: "bottomright" }).addTo(m);
    L.control.scale({ position: "bottomright", imperial: false }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    fitted.current = false;
    m.setView([36.8, 8.66], 13);
    return () => { m.remove(); map.current = null; base.current = null; layer.current = null; };
  }, [online]);

  // base layer + tile failure detection (no internet in the field -> offline map)
  useEffect(() => {
    const m = map.current;
    if (!m || !online) return;
    const src = tiles.find((t) => t.id === mode) ?? tiles[0];
    base.current?.remove();
    const t = L.tileLayer(src.url, { maxZoom: src.max_zoom ?? 19, attribution: src.attribution, subdomains: src.subdomains ?? "abc", crossOrigin: true });
    let ok = 0, bad = 0;
    t.on("tileload", () => { ok++; });
    t.on("tileerror", () => {
      bad++;
      if (bad >= 6 && ok === 0) { setNotice(`${src.name} tiles could not be loaded (no internet?). Showing the offline forest map.`); setModeState(OFFLINE); }
    });
    t.addTo(m);
    base.current = t;
  }, [mode, online, tiles]);

  // overlays: redrawn on every overview update
  useEffect(() => {
    const m = map.current, g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    draw(g, ov, (id) => onSel.current?.(id));
    if (!fitted.current) {
      const pts = [...ov.boxes.filter(valid).map(ll), ...[ov.site.gateway_pos, ov.site.drone_base, ov.site.spare_gateway_pos].filter(valid).map((p) => ll(p!))];
      if (pts.length) { m.fitBounds(L.latLngBounds(pts), { padding: [60, 60], maxZoom: 16 }); fitted.current = true; }
    }
  }, [ov, online]);

  const fit = () => {
    const m = map.current;
    if (!m) return;
    const pts = [...ov.boxes.filter(valid).map(ll), ...[ov.site.gateway_pos, ov.site.drone_base, ov.site.spare_gateway_pos].filter(valid).map((p) => ll(p!))];
    if (pts.length) m.flyToBounds(L.latLngBounds(pts), { padding: [60, 60], maxZoom: 16, duration: 0.6 });
  };
  const fireBox = ov.boxes.find((b) => ov.fire_boxes.includes(b.id));
  const focusFire = () => { if (map.current && fireBox) map.current.flyTo(ll(fireBox), 16, { duration: 0.6 }); };
  const wind = ov.fire?.wind_to_deg;

  return (
    <div className="live-map" style={{ ["--map-h" as string]: `${height}px` }}>
      <div className="map-toolbar" role="toolbar" aria-label="Map">
        <div className="seg" role="group" aria-label="Base map">
          {tiles.map((t) => <button key={t.id} className={mode === t.id ? "on" : undefined} aria-pressed={mode === t.id} onClick={() => setMode(t.id)}>{t.name}</button>)}
          <button className={mode === OFFLINE ? "on" : undefined} aria-pressed={mode === OFFLINE} onClick={() => setMode(OFFLINE)}>Offline</button>
        </div>
        {online && <button className="btn sm" onClick={fit}>Fit network</button>}
        {online && fireBox && <button className="btn sm danger" onClick={focusFire}>Go to fire</button>}
      </div>
      {notice && <div className="map-notice" role="status">{notice}</div>}
      {online ? (
        <div className="leaflet-wrap">
          <div ref={host} className="leaflet-host" aria-label={`Map of the network: ${ov.boxes.length} boxes${fireBox ? `, fire at ${fireBox.name}` : ""}`} />
          <div className="map-overlay compass" aria-hidden="true">
            <svg width="64" height="64" viewBox="-32 -32 64 64">
              <circle r="29" fill="var(--surface)" opacity=".94" stroke="var(--line-strong)" />
              <path d="M0-25 4-17h-8z" fill="var(--ink)" />
              {wind != null && <g transform={`rotate(${wind})`}><path d="M0 16V-15M-6-7 0-16 6-7" fill="none" stroke="var(--teal)" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" /></g>}
            </svg>
            <div className="wind-txt">{ov.fire?.wind_kmh != null ? `Wind ${Math.round(ov.fire.wind_kmh)} km/h` : "Wind"}<br /><i>direction simulated</i></div>
          </div>
          <div className="map-overlay legend" aria-hidden="true">
            <span><i className="dot" style={{ background: "var(--ok)" }} />Normal</span>
            <span><i className="dot" style={{ background: "var(--amber)" }} />Suspicion</span>
            <span><i className="dot" style={{ background: "var(--ember)" }} />Fire</span>
            <span><i className="dot" style={{ background: "var(--slate)" }} />Lost</span>
            <span><i className="ln good" />LoRa</span><span><i className="ln relay" />Relay</span>
            <span><i className="sq" />Spread 15/30/60 min</span>
          </div>
        </div>
      ) : (
        <SiteMap ov={ov} onSelect={onSelect} />
      )}
    </div>
  );
}

function chip(text: string, tone = "") {
  return L.divIcon({ className: "lm-chip-wrap", html: `<span class="lm-chip ${tone}">${esc(text)}</span>`, iconSize: [0, 0] });
}

function draw(g: L.LayerGroup, ov: Overview, select: (id: number) => void) {
  const active = ov.fire_boxes.length > 0 || !!ov.unacked_fire || ov.level.top === 3;
  const boxes = ov.boxes.filter(valid);
  const gw = valid(ov.site.gateway_pos) ? ll(ov.site.gateway_pos) : null;
  const fire = active ? ov.fire ?? {} : {};
  const fireBox = boxes.find((b) => ov.fire_boxes.includes(b.id));

  // spread isochrones (ellipse inscribed in the slow path's bounding box), largest first
  Object.entries(fire.isochrones ?? {}).sort((a, b) => +b[0] - +a[0]).forEach(([mins, v]) => {
    const c: L.LatLngTuple = [(v.bbox[0] + v.bbox[2]) / 2, (v.bbox[1] + v.bbox[3]) / 2];
    const ry = Math.abs(v.bbox[2] - v.bbox[0]) / 2, rx = Math.abs(v.bbox[3] - v.bbox[1]) / 2;
    const ring: L.LatLngTuple[] = Array.from({ length: 64 }, (_, i) => [c[0] + ry * Math.sin((i / 64) * 2 * Math.PI), c[1] + rx * Math.cos((i / 64) * 2 * Math.PI)]);
    const k = +mins;
    L.polygon(ring, { color: "#c2461a", weight: k === 15 ? 2.5 : 1.8, dashArray: k === 15 ? undefined : "8 6",
      fillColor: k === 15 ? "#5a2a17" : "#e0622a", fillOpacity: k === 15 ? 0.45 : k === 30 ? 0.22 : 0.1, interactive: false }).addTo(g);
    L.marker([c[0] + ry * 0.72, c[1] + rx * 0.72], { icon: chip(`${mins} min`, "ember"), interactive: false }).addTo(g);
  });

  // smoke drifting downwind, fire glow
  if (fireBox && fire.wind_to_deg != null) {
    const p = ll(fireBox);
    for (let i = 0; i < 7; i++) {
      L.circle(offset(p, 70 + i * 120, fire.wind_to_deg), { radius: 55 + i * 42, stroke: false, fillColor: "#7b7873", fillOpacity: 0.34 - i * 0.04,
        className: `lm-smoke s${i}`, interactive: false }).addTo(g);
    }
  }
  if (fireBox) L.circle(ll(fireBox), { radius: 110, stroke: false, fillColor: "#ff6a1f", fillOpacity: 0.35, className: "lm-glow", interactive: false }).addTo(g);

  // links: direct LoRa to the gateway, or through the nearest neighbour when the box is relayed; faint mesh between neighbours
  const direct = boxes.filter((b) => !b.relayed);
  const mesh = new Set<string>();
  boxes.forEach((b) => {
    const p = ll(b);
    boxes.filter((o) => o.id !== b.id).sort((x, y) => metres(p, ll(x)) - metres(p, ll(y))).slice(0, 2).forEach((o) => {
      const k = [Math.min(b.id, o.id), Math.max(b.id, o.id)].join("-");
      if (mesh.has(k)) return;
      mesh.add(k);
      L.polyline([p, ll(o)], { className: "lm-mesh", weight: 1.4, dashArray: "2 7", interactive: false }).addTo(g);
    });
    const q = quality(b);
    const recent = b.online && (b.age_s ?? 999) < 30;
    if (b.relayed) {
      const via = direct.filter((o) => o.id !== b.id).sort((x, y) => metres(p, ll(x)) - metres(p, ll(y)))[0];
      if (via) L.polyline([p, ll(via)], { className: `lm-link relay ${recent ? "flow" : ""}`, weight: 2.6, dashArray: "4 8", interactive: false }).addTo(g);
    } else if (gw) {
      L.polyline([p, gw], { className: `lm-link ${q} ${recent ? "flow" : ""}`, weight: 2.6, dashArray: "4 8", interactive: false }).addTo(g);
    }
  });

  // drone mission (simulated): curved path from the base to the target
  const base = valid(ov.site.drone_base) ? ll(ov.site.drone_base) : null;
  if (active && ov.mission && base) {
    const t = ll(ov.mission.target);
    const mid: L.LatLngTuple = [(base[0] + t[0]) / 2, (base[1] + t[1]) / 2];
    const ctrl: L.LatLngTuple = [mid[0] + (t[1] - base[1]) * 0.25, mid[1] - (t[0] - base[0]) * 0.25];
    const curve: L.LatLngTuple[] = Array.from({ length: 33 }, (_, i) => {
      const s = i / 32;
      return [(1 - s) ** 2 * base[0] + 2 * (1 - s) * s * ctrl[0] + s * s * t[0], (1 - s) ** 2 * base[1] + 2 * (1 - s) * s * ctrl[1] + s * s * t[1]];
    });
    L.polyline(curve, { className: "lm-drone", weight: 2.2, dashArray: "9 7", interactive: false }).addTo(g);
    L.marker(curve[16], { icon: L.divIcon({ className: "", html: `<span class="lm-pin drone"><svg viewBox="-12 -12 24 24" width="18" height="18"><path d="M-8-6h6M2-6h6M-5-6v3M5-6v3M-4 0h8l-2 5h-4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></span>`, iconSize: [26, 26], iconAnchor: [13, 13] }), interactive: false }).addTo(g);
    L.marker(curve[16], { icon: chip("Drone mission · simulated flight"), interactive: false }).addTo(g);
  }

  // source estimate
  if (fire.source && fire.source.used_as_ignition) {   // an indicative estimate (< 4 boxes) is listed in Response, not drawn
    const s = fire.source;
    L.marker([s.lat, s.lon], { icon: L.divIcon({ className: "", html: `<span class="lm-cross"></span>`, iconSize: [30, 30], iconAnchor: [15, 15] }), interactive: false }).addTo(g);
    L.marker([s.lat, s.lon], { icon: chip(s.used_as_ignition ? `Ignition estimate · ${s.n_boxes_detecting} boxes in the plume` : `Source estimate · indicative (${s.n_boxes_detecting} boxes)`), interactive: false }).addTo(g);
  }

  // infrastructure
  if (base) {
    L.marker(base, { icon: L.divIcon({ className: "", html: `<span class="lm-pin pad">H</span>`, iconSize: [30, 30], iconAnchor: [15, 15] }), keyboard: false }).addTo(g);
    L.marker(base, { icon: chip("Drone base"), interactive: false }).addTo(g);
  }
  if (valid(ov.site.spare_gateway_pos)) {
    const sp = ll(ov.site.spare_gateway_pos!);
    L.marker(sp, { icon: L.divIcon({ className: "", html: `<span class="lm-pin gw spare"><svg viewBox="-12 -12 24 24" width="20" height="20"><path d="M0 8V-5M-5-1a7 7 0 0 1 10 0M-8-5a11 11 0 0 1 16 0M-4 8h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></span>`, iconSize: [30, 30], iconAnchor: [15, 15] }), keyboard: false }).addTo(g);
    L.marker(sp, { icon: chip("Spare gateway · standby"), interactive: false }).addTo(g);
  }
  if (gw) {
    L.marker(gw, { icon: L.divIcon({ className: "", html: `<span class="lm-pin gw"><svg viewBox="-12 -12 24 24" width="20" height="20"><path d="M0 8V-5M-5-1a7 7 0 0 1 10 0M-8-5a11 11 0 0 1 16 0M-4 8h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></span>`, iconSize: [34, 34], iconAnchor: [17, 17] }), keyboard: false }).addTo(g);
    L.marker(gw, { icon: chip(ov.link.online ? `Gateway · online` : "Gateway · link offline", ov.link.online ? "strong" : "ember"), interactive: false }).addTo(g);
  }

  // boxes on top
  boxes.forEach((b) => {
    const st = stateOf(b);
    const why = (b.reasons ?? []).filter((r) => r !== "fwi").join(" + ");
    const status = st === "lost" ? "Lost" : st === "unknown" ? "No data" : st[0].toUpperCase() + st.slice(1);
    const html = `<div class="lm-box st-${st}${st === "fire" ? " burning" : ""}">
        <span class="ring"><i></i></span>
        <span class="lab"><b>${esc(b.name.split(",")[0])}</b><em>${esc(status)}${why ? " · " + esc(why) : ""}${b.relayed ? " · relayed" : ""}</em></span></div>`;
    const mk = L.marker(ll(b), { icon: L.divIcon({ className: "", html, iconSize: [34, 34], iconAnchor: [17, 17] }), title: `${b.name}: ${status}`, riseOnHover: true, zIndexOffset: st === "fire" ? 1000 : 500 });
    mk.on("click", () => select(b.id));
    mk.addTo(g);
  });
}
