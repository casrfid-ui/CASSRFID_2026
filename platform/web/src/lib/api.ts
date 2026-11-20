import type { AlertRow, AppConfig, CommandRow, EmailRow, Mission, Overview, RiskView, Sample, TimelineEvent } from "./types";

const TOKEN_KEY = "ffn.operatorToken";

export function operatorToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}
export function setOperatorToken(v: string) {
  try { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const tok = operatorToken();
  if (tok && path.startsWith("/api/ops/")) headers.Authorization = `Bearer ${tok}`;
  const r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : msg; } catch { /* not json */ }
    if (r.status === 401) msg = "Operator token missing or wrong (System → Operator access)";
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  config: () => call<AppConfig>("GET", "/api/config"),
  overview: () => call<Overview>("GET", "/api/overview"),
  alerts: (limit = 100) => call<AlertRow[]>("GET", `/api/alerts?limit=${limit}`),
  timeline: (limit = 200) => call<TimelineEvent[]>("GET", `/api/timeline?limit=${limit}`),
  series: (box: number, hours = 6) => call<Sample[]>("GET", `/api/boxes/${box}/series?hours=${hours}`),
  risk: () => call<RiskView>("GET", "/api/risk"),
  missions: () => call<Mission[]>("GET", "/api/missions"),
  emails: () => call<EmailRow[]>("GET", "/api/emails"),
  commands: () => call<CommandRow[]>("GET", "/api/commands"),
  ack: (alert_id?: string) => call<{ status: string }>("POST", "/api/ops/ack", alert_id ? { alert_id } : {}),
  command: (cmd: string, box: number, extra: Record<string, number> = {}) =>
    call<{ status: string; error?: string }>("POST", "/api/ops/command", { cmd, box, ...extra }),
  simWeather: (box: number, enable: boolean, wind_kmh: number, rain_mm: number) =>
    call<{ status: string }>("POST", "/api/ops/sim-weather", { box, enable, wind_kmh, rain_mm }),
  testSms: (text: string) => call<{ status: string }>("POST", "/api/ops/test-sms", { text }),
  testEmail: (to: string) => call<{ status: string }>("POST", "/api/ops/test-email", { to }),
};
