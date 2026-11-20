import { useEffect, useState } from "react";
import type { AppConfig, Overview, TimelineEvent } from "../lib/types";
import { api } from "../lib/api";
import { LiveMap } from "../components/LiveMap";
import { AlertsPanel, EvidencePanel, Timeline } from "../components/Panels";
import { BoxCard, BoxTile, sortBoxes } from "../components/BoxCard";
import { Card } from "../components/ui";

export function useGasHistory(ids: number[], hours = 1) {
  const [h, setH] = useState<Record<number, (number | null)[]>>({});
  const key = ids.join(",");
  useEffect(() => {
    let alive = true;
    const load = () => Promise.all(ids.map((id) => api.series(id, hours).then((s) => [id, s.map((x) => x.gas)] as const).catch(() => [id, []] as const)))
      .then((rows) => { if (alive) setH(Object.fromEntries(rows)); });
    load();
    const t = window.setInterval(load, 20000);
    return () => { alive = false; window.clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, hours]);
  return h;
}

export function Operations({ ov, timeline, config }: { ov: Overview; timeline: TimelineEvent[]; config: AppConfig | null }) {
  const gas = useGasHistory(ov.boxes.map((b) => b.id));
  return (
    <main className="page">
      <div className="grid-ops">
        <div className="col">
          <Card title="Site map" sub={`${ov.counts.online} of ${ov.counts.boxes} boxes online`} flush id="h-map"
                right={ov.fire.isochrones && (ov.fire_boxes.length > 0 || ov.unacked_fire) ? <span className="badge lv lv-3">Spread forecast 15 · 30 · 60 min</span> : undefined}>
            <LiveMap ov={ov} config={config} onSelect={(id) => { location.hash = `#/boxes/${id}`; }} />
          </Card>
          {ov.boxes.length <= 2 ? (
            <div className="row2">{ov.boxes.map((b) => <BoxCard key={b.id} box={b} gasHistory={gas[b.id]} />)}</div>
          ) : (
            <section aria-label="Boxes" className="stack" style={{ gap: 10 }}>
              <div className="inline" style={{ justifyContent: "space-between" }}>
                <h2 style={{ fontSize: 13 }}>Boxes <span className="muted" style={{ fontWeight: 500 }}>· worst state first</span></h2>
                <a className="note" href="#/boxes">all details</a>
              </div>
              <div className="tiles">{sortBoxes(ov.boxes).map((b) => <BoxTile key={b.id} box={b} gasHistory={gas[b.id]} />)}</div>
            </section>
          )}
        </div>
        <div className="col">
          <AlertsPanel alerts={ov.alerts} boxes={ov.boxes} />
          <EvidencePanel fusion={ov.fusion} boxes={ov.boxes} />
          <Timeline events={timeline} boxes={ov.boxes} />
        </div>
      </div>
    </main>
  );
}
