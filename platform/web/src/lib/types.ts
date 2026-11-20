// Shapes returned by the dashboard backend (platform/server, ffn_dashboard).
export type Level = 0 | 1 | 2 | 3 | 4 | 5;
export type BoxState = "normal" | "suspicion" | "fire" | "unknown";
export type Health = "ok" | "fault" | "low" | "hot" | "weak" | "down" | "unknown";

export interface Box {
  id: number;
  name: string;
  lat: number;
  lon: number;
  pos_source: "survey" | "gps";
  online: boolean;
  age_s: number | null;
  lost: boolean;
  last_gasp: boolean;
  rssi: number | null;
  snr: number | null;
  frames: number;
  relayed?: boolean;
  weather_simulated: boolean;
  levels: Level[];
  has_status: boolean;
  state?: BoxState;
  mode?: "eco" | "alert" | "survival" | "unknown";
  reasons?: string[];
  gas?: { score: number | null; class: string; bands: number[] };
  flame?: boolean;
  camera?: { label: string; valid: boolean; conf: number | null };
  fwi?: FwiReading;
  battery_pct?: number | null;
  flags?: string[];
  health: Record<"gas" | "flame" | "camera" | "battery" | "housing" | "supply" | "link", Health>;
  weather?: {
    temp_c: number | null; rh: number | null; wind_kmh: number | null; rain_mm: number | null;
    codes: { ffmc: number | null; dmc: number | null; dc: number | null; isi: number | null; bui: number | null };
    provisional: boolean;
  };
  vision?: { label: string; conf: number; ms: number; t: number };
}

export interface FwiReading { value: number | null; danger: number | null; danger_name: string; provisional: boolean }

export interface ActiveAlert { level: Level; name: string; box: number; reason: string }

export interface AlertRow {
  id: number; alert_id: string; level: Level; level_name: string; box: number; reason: string;
  lat: number; lon: number; text: string; t: number; received: number; acked: boolean; acked_at: number | null;
}

export interface TimelineEvent { id: number; t: number; kind: string; box: number; level: number; text: string; data: Record<string, unknown> }

export interface MissionItem { seq: number; command: number; name: string; lat?: number; lon?: number; alt?: number; servo?: number; pwm?: number }
export interface Mission {
  id: string; simulated: boolean; created?: number; received?: number; note?: string;
  target: { lat: number; lon: number }; base: { lat: number; lon: number }; items: MissionItem[];
}

export interface FireGeometry {
  wind_kmh?: number; wind_to_deg?: number; wind_direction_simulated?: boolean;
  source?: { lat: number; lon: number; area50_m2: number; area90_m2: number; n_boxes_detecting: number; used_as_ignition: boolean; note: string };
  isochrones?: Record<string, { area_m2: number; bbox: [number, number, number, number] }>;
  ignition?: { lat: number; lon: number };
}

export interface Fusion {
  statistic: number; posterior: number; llr_sum: number; prior: number; danger: number;
  confirmed: boolean; suspected: boolean; contributions: { box: number; witness: string; llr: number }[];
}

export interface LinkInfo {
  mode: "pull" | "push"; online: boolean; last_ok: number; last_push: number; error: string;
  polls: number; failures: number; age_s: number | null; gateway_url: string | null;
}

export interface Overview {
  t: number;
  site: { name: string; drone_base: { lat: number; lon: number }; gateway_pos: { lat: number; lon: number }; spare_gateway_pos?: { lat: number; lon: number }; timezone: string };
  link: LinkInfo;
  gateway: {
    id: number | null; snapshot_t: number | null; bridge: Record<string, unknown> | null;
    stats: Record<string, number>; episode: string | null; outbox_pending: number;
    uplink?: { ok: number; fail: number; error: string; commands: number } | null;
  };
  level: { top: Level; name: string };
  alerts: ActiveAlert[];
  fire_boxes: number[];
  fusion: Fusion | null;
  boxes: Box[];
  counts: { boxes: number; online: number };
  fwi_worst: FwiReading | null;
  fire: FireGeometry;
  mission: Mission | null;
  unacked_fire: AlertRow | null;
  mail: { smtp: boolean };
  comms?: { sms: number; sms_last: number | null; emails: number; emails_last: number | null; email_status: string | null; missions: number };
}

export interface BridgeInfo {
  uptime_s: number; sbc_up: boolean; modem_ready: boolean; alert_armed: boolean; have_time: boolean;
  pending: number; csq: number; frames_rx: number; acks_tx: number; crc_errors: number;
}

export interface ForecastDay { day: number; q10: number; q50: number; q90: number; p_high: number; class_median: number }
export interface RiskView {
  fwi_forecast: Record<string, ForecastDay[]>;
  fire: FireGeometry;
  errors: Record<string, string>;
  updated: number;
  models: Record<string, unknown>;
}

export interface Sample {
  box: number; t: number; gas: number | null; fwi: number | null; danger: number | null; battery: number | null;
  rssi: number | null; snr: number | null; temp: number | null; rh: number | null; wind: number | null; rain: number | null; state: number | null;
}

export interface EmailRow { id: number; t: number; recipient: string; subject: string; body: string; status: string; error: string; alert_id: string }
export interface CommandRow { id: number; t: number; name: string; body: Record<string, unknown>; status: string; result: unknown; done_t: number | null }
export interface TileSource { id: string; name: string; url: string; attribution: string; max_zoom?: number; subdomains?: string }
export interface AppConfig { site: string; timezone: string; operator_token_required: boolean; smtp: boolean; link_mode: "pull" | "push"; map_tiles?: TileSource[] }
