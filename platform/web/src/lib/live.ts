import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { AlertRow, AppConfig, Overview, TimelineEvent } from "./types";
import { humanReason, setTimezone } from "./format";

export type Conn = "connecting" | "live" | "reconnecting";
export interface Toast { id: number; tone: "fire" | "warn" | "info" | "ok" | "error"; title: string; body?: string }

/** Live state of the console: one EventSource, initial REST loads, toasts, and a fire alarm sound (opt-in). */
export function useLive() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [conn, setConn] = useState<Conn>("connecting");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [sound, setSound] = useState<boolean>(() => { try { return localStorage.getItem("ffn.sound") === "1"; } catch { return false; } });
  const soundRef = useRef(sound);
  soundRef.current = sound;
  const toastId = useRef(0);

  const toast = useCallback((t: Omit<Toast, "id">, ms = 6000) => {
    const id = ++toastId.current;
    setToasts((xs) => [...xs.slice(-3), { ...t, id }]);
    window.setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), ms);
  }, []);
  const dismiss = useCallback((id: number) => setToasts((xs) => xs.filter((x) => x.id !== id)), []);

  const toggleSound = useCallback(() => {
    setSound((s) => { const n = !s; try { localStorage.setItem("ffn.sound", n ? "1" : "0"); } catch { /* ignore */ } if (n) beep(660, 0.12); return n; });
  }, []);

  const refresh = useCallback(async () => {
    const [o, a, tl] = await Promise.allSettled([api.overview(), api.alerts(100), api.timeline(200)]);
    if (o.status === "fulfilled") setOverview(o.value);
    if (a.status === "fulfilled") setAlerts(a.value);
    if (tl.status === "fulfilled") setTimeline(tl.value);
  }, []);

  useEffect(() => {
    api.config().then((c) => { setConfig(c); setTimezone(c.timezone); }).catch(() => undefined);
    refresh();
    let es: EventSource | null = null;
    let retry = 0;
    let timer = 0;
    const open = () => {
      es = new EventSource("/api/stream");
      es.addEventListener("open", () => { setConn("live"); if (retry > 0) refresh(); retry = 0; });
      es.addEventListener("error", () => {
        setConn("reconnecting");
        es?.close();
        timer = window.setTimeout(open, Math.min(15000, 1000 * 2 ** retry++));
      });
      es.addEventListener("overview", (e) => setOverview(JSON.parse((e as MessageEvent).data)));
      es.addEventListener("event", (e) => {
        const ev: TimelineEvent = JSON.parse((e as MessageEvent).data);
        setTimeline((xs) => (xs.some((x) => x.id === ev.id) ? xs : [ev, ...xs].slice(0, 400)));
      });
      es.addEventListener("alert", (e) => {
        const a: AlertRow = JSON.parse((e as MessageEvent).data);
        setAlerts((xs) => [a, ...xs].slice(0, 200));
        if (a.level === 3) {
          toast({ tone: "fire", title: `Fire confirmed · Box ${a.box}`, body: humanReason(a.reason) }, 12000);
          if (soundRef.current) alarm();
          notify(`Fire confirmed · Box ${a.box}`, humanReason(a.reason));
        } else if (a.level === 4) toast({ tone: "warn", title: `Box ${a.box} lost`, body: humanReason(a.reason) });
        else if (a.level === 2) toast({ tone: "warn", title: `Suspicion · Box ${a.box}`, body: humanReason(a.reason) });
      });
      es.addEventListener("mission", (e) => {
        const m = JSON.parse((e as MessageEvent).data);
        toast({ tone: "info", title: "Drone mission ready", body: `Mission ${m.id} · simulated flight` });
      });
      es.addEventListener("email", (e) => {
        const m = JSON.parse((e as MessageEvent).data);
        toast({ tone: m.status === "failed" ? "error" : "info", title: `Email ${m.status}`, body: m.to });
      });
      es.addEventListener("command", (e) => {
        const c = JSON.parse((e as MessageEvent).data);
        toast({ tone: c.status === "done" ? "ok" : "info", title: `Command ${c.name.replace("_", " ")}: ${c.status}`, body: c.error ?? c.note });
      });
    };
    open();
    const poll = window.setInterval(() => { if (es?.readyState !== EventSource.OPEN) refresh(); }, 10000);
    return () => { es?.close(); window.clearTimeout(timer); window.clearInterval(poll); };
  }, [refresh, toast]);

  return { overview, alerts, timeline, config, conn, toasts, toast, dismiss, sound, toggleSound, refresh };
}

let ctx: AudioContext | null = null;
function beep(freq: number, dur: number, when = 0) {
  try {
    ctx = ctx ?? new AudioContext();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "sine"; o.frequency.value = freq;
    const t = ctx.currentTime + when;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + dur + 0.05);
  } catch { /* audio blocked */ }
}
function alarm() { [0, 0.35, 0.7].forEach((w) => { beep(880, 0.22, w); beep(660, 0.18, w + 0.17); }); }
function notify(title: string, body: string) {
  try {
    if ("Notification" in window && Notification.permission === "granted" && document.hidden) new Notification(title, { body });
  } catch { /* unsupported */ }
}
