import { useCallback, useEffect, useState } from "react";
import { useLive } from "./lib/live";
import { api } from "./lib/api";
import { FireBanner, StatusStrip, Toasts, TopBar, type Route } from "./components/Chrome";
import { Operations } from "./views/Operations";
import { Boxes } from "./views/Boxes";
import { Response } from "./views/Response";
import { System } from "./views/System";
import { Network } from "./views/Network";
import { LEVEL_WORD } from "./lib/format";

function parseHash(): { route: Route; id?: number } {
  const [, a, b] = location.hash.replace(/^#/, "").split("/");
  if (a === "boxes") return { route: "boxes", id: b ? Number(b) : undefined };
  if (a === "response" || a === "system" || a === "network") return { route: a };
  return { route: "ops" };
}

function initialTheme() {
  try { const t = localStorage.getItem("ffn.theme"); if (t) return t; } catch { /* ignore */ }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const live = useLive();
  const { overview: ov, toast } = live;
  const [loc, setLoc] = useState(parseHash());
  const [theme, setThemeState] = useState(initialTheme);
  useEffect(() => { const f = () => { setLoc(parseHash()); window.scrollTo(0, 0); }; window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const setTheme = (t: string) => { setThemeState(t); try { localStorage.setItem("ffn.theme", t); } catch { /* ignore */ } };

  // the tab title carries the level, so a fire is visible from another tab
  useEffect(() => {
    if (!ov) return;
    const lv = ov.level.top;
    document.title = lv === 3 ? `● FIRE · ${ov.site.name}` : lv ? `${LEVEL_WORD[lv]} · Forest Fire Network` : "Forest Fire Network · Operations";
  }, [ov]);

  // ask once for desktop notifications when the operator turns the alarm on
  useEffect(() => { if (live.sound && "Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => undefined); }, [live.sound]);

  const ack = useCallback(async () => {
    try {
      const r = await api.ack(ov?.unacked_fire?.alert_id);
      toast({ tone: "ok", title: "Fire acknowledged", body: r.status === "queued" ? "Sent with the next gateway exchange" : "The gateway stops repeating the alert" });
    } catch (e) { toast({ tone: "error", title: "Acknowledge failed", body: (e as Error).message }); }
  }, [ov?.unacked_fire?.alert_id, toast]);

  return (
    <div className="shell">
      <a className="sr-only" href="#main">Skip to content</a>
      <TopBar route={loc.route} ov={ov} conn={live.conn} theme={theme} setTheme={setTheme} sound={live.sound} toggleSound={live.toggleSound} />
      {ov ? <StatusStrip ov={ov} /> : <div />}
      {ov ? <FireBanner ov={ov} onAck={ack} /> : <div />}
      <div id="main">
        {!ov ? (
          <main className="page"><div className="card"><div className="empty">Connecting to the dashboard backend…</div></div></main>
        ) : loc.route === "boxes" ? <Boxes ov={ov} id={loc.id} toast={toast} />
          : loc.route === "response" ? <Response ov={ov} config={live.config} />
          : loc.route === "network" ? <Network ov={ov} config={live.config} />
          : loc.route === "system" ? <System ov={ov} config={live.config} toast={toast} />
          : <Operations ov={ov} timeline={live.timeline} config={live.config} />}
      </div>
      <Toasts toasts={live.toasts} dismiss={live.dismiss} />
    </div>
  );
}
