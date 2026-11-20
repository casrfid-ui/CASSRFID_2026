import type { Level } from "./types";

let TZ = "Africa/Tunis";
export const setTimezone = (tz: string) => { if (tz) TZ = tz; };

const timeFmt = () => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit" });
const dateTimeFmt = () => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export const clock = (t: number) => timeFmt().format(new Date(t * 1000));
export const stamp = (t: number) => dateTimeFmt().format(new Date(t * 1000));

export function ago(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return "never";
  const s = Math.max(0, Math.round(seconds));
  if (s < 5) return "just now";
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export const coord = (lat: number, lon: number) =>
  `${Math.abs(lat).toFixed(5)}°${lat >= 0 ? "N" : "S"} ${Math.abs(lon).toFixed(5)}°${lon >= 0 ? "E" : "W"}`;

export const num = (v: number | null | undefined, d = 1, unit = "") =>
  v == null || !isFinite(v) ? "–" : `${v.toFixed(d)}${unit}`;

export const area = (m2: number) => (m2 >= 10000 ? `${(m2 / 10000).toFixed(1)} ha` : `${Math.round(m2).toLocaleString("en-GB")} m²`);

export const LEVEL_LABEL: Record<Level, string> = {
  0: "All clear", 1: "L1 · High fire weather", 2: "L2 · Suspicion", 3: "L3 · Fire confirmed", 4: "L4 · Box lost", 5: "L5 · Maintenance",
};
export const LEVEL_SHORT: Record<Level, string> = { 0: "Clear", 1: "L1", 2: "L2", 3: "L3", 4: "L4", 5: "L5" };
export const LEVEL_WORD: Record<Level, string> = { 0: "Clear", 1: "High risk", 2: "Suspicion", 3: "Fire", 4: "Box lost", 5: "Maintenance" };

// EFFIS fire danger classes, computed on the box (edges 5.2 / 11.2 / 21.3 / 38 / 50)
export const DANGER = [
  { name: "Very low", lo: 0, hi: 5.2 }, { name: "Low", lo: 5.2, hi: 11.2 }, { name: "Moderate", lo: 11.2, hi: 21.3 },
  { name: "High", lo: 21.3, hi: 38 }, { name: "Very high", lo: 38, hi: 50 }, { name: "Extreme", lo: 50, hi: 80 },
];

export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export const KIND_LABEL: Record<string, string> = {
  alert: "Alert", cleared: "Cleared", sms: "SMS", sms_result: "SMS status", drone: "Drone", vision: "Vision",
  operator: "Operator", cmd: "Command", bad_frame: "Bad frame", thresholds: "Thresholds",
};

/** Gateway reason strings are terse; this turns them into operator language. */
export function humanReason(r: string): string {
  let t = r.replace(/^(box \d+: )+/i, "");
  t = t.replace(/box FIRE \(([^)]*)\)/i, (_, x: string) => `Fire decided on the box: ${listReasons(x)}`);
  t = t.replace(/box suspicion \(([^)]*)\)/i, (_, x: string) => `Suspicion on the box: ${listReasons(x)}`);
  t = t.replace(/FWI ([\d.]+) danger class (\d)/i, (_, v: string, c: string) => `FWI ${v}, ${(DANGER[+c]?.name ?? "").toLowerCase()} fire danger`);
  t = t.replace(/fusion S=([-\d.]+) \(posterior ([\d.]+)\)/i, (_, v: string, p: string) => `Evidence fusion: score ${v}, fire probability ${(+p * 100).toFixed(1)} %`);
  t = t.replace(/fusion posterior ([\d.]+)/i, (_, p: string) => `Evidence fusion: fire probability ${(+p * 100).toFixed(1)} %`);
  t = t.replace(/^battery low$/i, "Battery low: box moves to Survival mode below 15 %");
  return t ? t[0].toUpperCase() + t.slice(1) : t;
}
const listReasons = (x: string) => x.split("+").filter((s) => s && s !== "none").map((s) => (s === "fwi" ? "FWI" : s)).join(" + ");
