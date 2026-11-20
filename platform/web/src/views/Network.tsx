import type { ReactNode } from "react";
import type { AppConfig, Box, BridgeInfo, Overview } from "../lib/types";
import { ago, cap, num } from "../lib/format";
import { Card } from "../components/ui";
import { LiveMap } from "../components/LiveMap";

const STATE_FILL: Record<string, string> = { normal: "var(--ok)", suspicion: "var(--amber)", fire: "var(--ember)", unknown: "var(--slate)" };
const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

type Tone = "live" | "idle" | "down" | "sim";

/** One link of the chain: path, state, label, and packets travelling along it when it carries traffic. */
function Edge({ d, tone, label, lx, ly, pkts = 0, dur = 2.2, fire = false, reverse = false }: {
  d: string; tone: Tone; label?: string; lx?: number; ly?: number; pkts?: number; dur?: number; fire?: boolean; reverse?: boolean;
}) {
  return (
    <g>
      <path className={`edge ${tone}`} d={d} />
      {!reduced && tone === "live" && Array.from({ length: pkts }, (_, i) => (
        <circle key={i} r="4.2" className={`pkt${fire ? " fire" : ""}`}>
          <animateMotion dur={`${dur}s`} repeatCount="indefinite" begin={`${-(dur / pkts) * i}s`} path={d}
                         keyPoints={reverse ? "1;0" : "0;1"} keyTimes="0;1" calcMode="linear" />
        </circle>
      ))}
      {label && <text className="elabel" x={lx} y={ly} textAnchor="middle">{label}</text>}
    </g>
  );
}

function Node({ x, y, w, h, eyebrow, title, lines, accent, dashed, href, children }: {
  x: number; y: number; w: number; h: number; eyebrow: string; title: string; lines: string[]; accent?: string; dashed?: boolean; href?: string; children?: ReactNode;
}) {
  const body = (
    <g>
      <rect className="node" x={x} y={y} width={w} height={h} rx="12" strokeDasharray={dashed ? "6 5" : undefined} />
      {accent && <rect x={x} y={y + 12} width="4" height={h - 24} rx="2" fill={accent} />}
      <text className="eyebrow" x={x + 18} y={y + 22}>{eyebrow}</text>
      <text className="t1" x={x + 18} y={y + 42}>{title}</text>
      {lines.map((l, i) => <text key={i} className={i === lines.length - 1 ? "t3" : "t2"} x={x + 18} y={y + 62 + i * 18}>{l}</text>)}
      {children}
    </g>
  );
  return href ? <a href={href} aria-label={`${title}: ${lines.join(", ")}`}>{body}</a> : body;
}

function Pill({ x, y, text, fill }: { x: number; y: number; text: string; fill: string }) {
  const w = text.length * 7 + 18;
  return (
    <g>
      <rect x={x - w} y={y - 11} width={w} height="22" rx="11" fill={fill} />
      <text x={x - w / 2} y={y + 4} textAnchor="middle" fontSize="11.5" fontWeight="700" fill="#fff">{text}</text>
    </g>
  );
}

const csqDbm = (csq: number) => (csq >= 0 && csq <= 31 ? -113 + 2 * csq : null);

export function Network({ ov, config }: { ov: Overview; config: AppConfig | null }) {
  const boxes = ov.boxes;
  const br = ov.gateway.bridge as unknown as BridgeInfo | null;
  const fire = ov.level.top === 3;
  const linkOk = ov.link.online;
  const c = ov.comms;
  const boxTone = (b: Box): Tone => (!b.online ? "down" : (b.age_s ?? 999) < 30 ? "live" : "idle");
  const PITCH = 68, Y0 = 84, BX = 84, BW = 250, BH = 58;
  const shown = [...boxes].sort((x, y) => x.id - y.id);
  const yOf = (i: number) => Y0 + i * PITCH;
  const spareY = Y0 + shown.length * PITCH + 8;
  const H = Math.max(600, spareY + 96);
  const dist = (a: Box, b: Box) => Math.hypot(a.lat - b.lat, (a.lon - b.lon) * Math.cos((a.lat * Math.PI) / 180));
  const smsRecent = c?.sms_last != null && ov.t - c.sms_last < 120;
  const mailRecent = c?.emails_last != null && ov.t - c.emails_last < 120;
  const sbcUp = br ? br.sbc_up : linkOk;
  const dbm = br ? csqDbm(br.csq) : null;

  return (
    <main className="page">
      <Card title="Network, end to end" sub="every element of the chain, live: sensing → LoRa → gateway → mobile network → people and drone" flush id="h-net">
        <div className="net-scroll"><svg className="net" viewBox={`0 0 1240 ${H}`} role="img" aria-label="Live diagram of the whole network">
          {/* columns */}
          <text className="eyebrow" x="84" y="60">Edge · {shown.length} boxes in the forest</text>
          <text className="eyebrow" x="420" y="40">Gateway · on the ridge</text>
          <text className="eyebrow" x="860" y="60">People and response</text>

          {/* links first, nodes paint over them */}
          <text className="elabel" x="356" y="74" textAnchor="middle">LoRa 433 MHz</text>
          {shown.map((b, i) => {
            const y = yOf(i) + BH / 2;
            if (b.relayed) {
              const direct = shown.map((o, j) => ({ o, j })).filter(({ o }) => !o.relayed && o.id !== b.id);
              const via = direct.sort((p, q) => dist(b, p.o) - dist(b, q.o))[0];
              if (!via) return null;
              const y2 = yOf(via.j) + BH / 2;
              return <Edge key={b.id} d={`M${BX},${y} C${BX - 40},${y} ${BX - 40},${y2} ${BX},${y2}`} tone={boxTone(b)} pkts={1} dur={2.2}
                           label={`relay via ${via.o.id}`} lx={BX - 42} ly={(y + y2) / 2 + 4} />;
            }
            const ty = 110 + (i * 80) / Math.max(1, shown.length - 1);
            return <Edge key={b.id} d={`M${BX + BW},${y} C${BX + BW + 60},${y} 370,${ty} 420,${ty}`} tone={boxTone(b)}
                         pkts={b.state === "fire" ? 3 : 1} dur={b.state === "fire" ? 1.4 : 2.6} fire={b.state === "fire"} />;
          })}
          <Edge d="M565,210 L565,236" tone={br ? "live" : "idle"} pkts={1} dur={1} />
          <Edge d="M565,366 L565,392" tone={sbcUp ? "live" : "idle"} pkts={1} dur={1} />
          <Edge d="M710,425 C790,425 780,125 860,125" tone={linkOk ? "live" : "down"} pkts={2} dur={2.4} label={linkOk ? `2G data · ${ov.link.mode}` : "2G data · down"} lx={798} ly={196} reverse={ov.link.mode === "pull"} />
          <Edge d="M710,455 C800,455 780,245 860,245" tone={smsRecent ? "live" : br?.modem_ready ?? linkOk ? "idle" : "down"} pkts={2} dur={1.6} fire label="GSM SMS" lx={812} ly={300} />
          <Edge d="M1160,140 C1205,140 1205,356 1160,356" tone={mailRecent ? "live" : "idle"} pkts={1} dur={1.4} />
          <text className="elabel" x="1218" y="250" textAnchor="middle" transform="rotate(90 1218 250)">{ov.mail.smtp ? "SMTP" : "email, logged"}</text>
          <Edge d="M710,300 C800,300 780,480 860,480" tone={ov.mission && fire ? "sim" : "idle"} label="MAVLink · simulated" lx={806} ly={455} />

          {/* edge boxes */}
          {shown.map((b, i) => {
            const st = b.lost ? "unknown" : b.state ?? "unknown";
            const y = yOf(i);
            return (
              <a key={b.id} href={`#/boxes/${b.id}`} aria-label={`${b.name}: ${b.lost ? "lost" : st}`}>
                <rect className="node" x={BX} y={y} width={BW} height={BH} rx="10" strokeDasharray={b.lost ? "5 4" : undefined} />
                <rect x={BX} y={y + 10} width="4" height={BH - 20} rx="2" fill={STATE_FILL[st]} />
                <text className="t1" x={BX + 16} y={y + 23} style={{ fontSize: 13 }}>{b.name}</text>
                <text className="t3" x={BX + 16} y={y + 43}>{`${b.battery_pct ?? "–"} % · ${b.rssi ?? "–"} dBm · ${b.lost ? "silent" : ago(b.age_s)}`}</text>
                <Pill x={BX + BW - 8} y={y + 18} text={b.lost ? "Lost" : st === "unknown" ? "No data" : cap(st)} fill={STATE_FILL[st]} />
              </a>
            );
          })}
          <Node x={BX} y={spareY} w={BW} h={84} eyebrow="Failover" title="Spare gateway" dashed lines={["standby, takes over if this one is lost", "not powered in the demo"]} />

          {/* gateway */}
          <rect className="frame" x="400" y="52" width="330" height="510" rx="16" />
          <Node x={420} y={84} w={290} h={126} eyebrow="Always on" title="ESP32 bridge + RA-02" accent="var(--forest-2)"
                lines={br ? [`acks ${br.acks_tx} · CRC errors ${br.crc_errors}`, `alert ${br.alert_armed ? "armed · emergency SMS ready" : "idle"} · queue ${br.pending}`, `uptime ${Math.round(br.uptime_s / 60)} min`]
                          : ["acks every alert in about 120 ms", "sends the SMS itself if the SBC is down", "no bridge telemetry in this setup"]} />
          <Node x={420} y={236} w={290} h={130} eyebrow={sbcUp ? "Running" : "Sleeping (power-gated)"} title="Khadas VIM4 / Pi 4" accent={sbcUp ? "var(--forest-2)" : "var(--slate)"}
                lines={[`fast path: ${ov.level.name}`, `fusion S ${num(ov.fusion?.statistic ?? null, 2)} / 2.94 · p ${num((ov.fusion?.posterior ?? 0) * 100, 1)} %`, `slow path: forecast, spread, vision`,
                        `${ov.gateway.stats.rx ?? 0} frames · ${ov.gateway.stats.dup ?? 0} dup · ${ov.gateway.stats.bad ?? 0} bad`]} />
          <Node x={420} y={392} w={290} h={112} eyebrow="Mobile network" title="SIM800L modem" accent={(br?.modem_ready ?? linkOk) ? "var(--forest-2)" : "var(--ember)"}
                lines={[br ? `signal CSQ ${br.csq}${dbm != null ? ` (${dbm} dBm)` : ""}` : "signal: not reported", `outbox pending ${ov.gateway.outbox_pending}`, `SMS sent ${c?.sms ?? 0}`]} />
          <text className="t3" x="420" y="540">UART · HDLC framing · CRC-16 between bridge and SBC</text>

          {/* endpoints */}
          <Node x={860} y={70} w={300} h={110} eyebrow="This console" title="Operator dashboard" accent={linkOk ? "var(--forest-2)" : "var(--ember)"}
                lines={[linkOk ? `gateway data ${ago(ov.link.age_s)}` : `no gateway data · ${ov.link.error || "offline"}`, `mode ${ov.link.mode === "pull" ? "pull (LAN)" : "push (NAT-friendly uplink)"}`, `${ov.counts.online}/${ov.counts.boxes} boxes online`]} />
          <Node x={860} y={200} w={300} h={92} eyebrow="Phones" title="Operator SMS" accent={smsRecent ? "var(--ember)" : "var(--line-strong)"}
                lines={[`${c?.sms ?? 0} fire SMS sent`, c?.sms_last ? `last ${ago(ov.t - c.sms_last)}` : "none yet"]} />
          <Node x={860} y={310} w={300} h={92} eyebrow="Inbox" title="Alert email" accent={mailRecent ? "var(--teal)" : "var(--line-strong)"}
                lines={[`${c?.emails ?? 0} emails · ${ov.mail.smtp ? "SMTP" : "recorded (no SMTP)"}`, c?.emails_last ? `last ${ago(ov.t - c.emails_last)} · ${c.email_status}` : "none yet"]} />
          <Node x={860} y={420} w={300} h={112} eyebrow="Response" title="Mini drone" href="#/response" accent={ov.mission && fire ? "var(--ember)" : "var(--line-strong)"}
                lines={ov.mission && fire ? [`mission ${ov.mission.id} ready`, "flight simulated · release mechanism built", `${ov.mission.items.length} MAVLink items`]
                                          : ["standby at the drone base", "mission built on a confirmed fire", "flight simulated in the demo"]} />
        </svg></div>
      </Card>

      <div className="row2">
        <Card title="Radio links" sub="LoRa 433 MHz, 16-byte frames" flush id="h-radio">
          <table className="tbl">
            <thead><tr><th>Box</th><th className="r">RSSI</th><th className="r">SNR</th><th>Quality</th><th className="r">Frames</th><th>Last frame</th></tr></thead>
            <tbody>
              {boxes.map((b) => {
                const r = b.rssi ?? -150, q = !b.online ? ["Down", "lv-3"] : r >= -105 ? ["Good", "lv-0"] : r >= -115 ? ["Fair", "lv-2"] : ["Weak", "lv-3"];
                return (
                  <tr key={b.id}>
                    <td><a href={`#/boxes/${b.id}`}>{b.name}</a></td>
                    <td className="r mono">{b.rssi ?? "–"} dBm</td><td className="r mono">{num(b.snr, 1)} dB</td>
                    <td><span className={`badge lv ${q[1]}`}>{q[0]}</span></td>
                    <td className="r mono">{b.frames}</td><td>{ago(b.age_s)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="card-b" style={{ paddingTop: 12 }}><span className="note">Below −115 dBm or −15 dB SNR the gateway raises a maintenance alert (L5); a box that hears no acknowledgement relays through its neighbour.</span></div>
        </Card>
        <Card title="How an alert travels" id="h-path">
          <ol className="stack" style={{ margin: 0, paddingLeft: 18, gap: 8 }}>
            <li><b>Box decides</b> from gas, flame vote and camera, then sends an ALERT frame with its reasons, repeated until acknowledged.</li>
            <li><b>Bridge acknowledges</b> in about 120 ms and wakes the SBC; if nothing takes over in 60 s it sends the SMS itself.</li>
            <li><b>SBC fuses</b> both boxes with the fire-weather prior, sets the level, writes SMS, email, drone mission and spread map.</li>
            <li><b>Mobile network</b> carries SMS over GSM (works without data) and the dashboard traffic over 2G data, with retries.</li>
            <li><b>Operator acknowledges</b> here; the command goes back to the gateway and down to the box over LoRa.</li>
          </ol>
        </Card>
      </div>

      <Card title="Network on the map" sub="box positions from GPS, LoRa links, mesh relays and the response assets" flush id="h-forest">
        <LiveMap ov={ov} config={config} onSelect={(id) => { location.hash = `#/boxes/${id}`; }} />
      </Card>
    </main>
  );
}
