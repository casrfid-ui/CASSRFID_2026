import { Fragment, useEffect, useState } from "react";
import type { AppConfig, CommandRow, EmailRow, Overview } from "../lib/types";
import { api, operatorToken, setOperatorToken } from "../lib/api";
import { ago, stamp } from "../lib/format";
import { Card, Empty } from "../components/ui";
import type { Toast } from "../lib/live";

export function System({ ov, config, toast }: { ov: Overview; config: AppConfig | null; toast: (t: Omit<Toast, "id">) => void }) {
  const [emails, setEmails] = useState<EmailRow[]>([]);
  const [cmds, setCmds] = useState<CommandRow[]>([]);
  const [models, setModels] = useState<Record<string, unknown>>({});
  const [to, setTo] = useState("");
  const [sms, setSms] = useState("Test SMS from the forest fire network");
  const [tok, setTok] = useState(operatorToken());
  useEffect(() => {
    let alive = true;
    const load = () => Promise.all([api.emails(), api.commands(), api.risk()]).then(([e, c, r]) => {
      if (alive) { setEmails(e); setCmds(c); setModels(r.models ?? {}); }
    }).catch(() => undefined);
    load();
    const t = window.setInterval(load, 8000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);
  const l = ov.link, g = ov.gateway;
  const run = async (p: Promise<{ status: string }>, what: string) => {
    try { const r = await p; toast({ tone: "ok", title: `${what}: ${r.status}` }); }
    catch (e) { toast({ tone: "error", title: `${what} failed`, body: (e as Error).message }); }
  };
  return (
    <main className="page">
      <div className="row3">
        <Card title="Gateway link" id="h-link" right={<span className={`badge lv ${l.online ? "lv-0" : "lv-3 strong"}`}>{l.online ? "Online" : "Offline"}</span>}>
          <dl className="kv-list">
            <dt>Mode</dt><dd>{l.mode === "pull" ? "Pull: dashboard polls the gateway API" : "Push: gateway uplinks snapshots (NAT friendly)"}</dd>
            {l.gateway_url && <><dt>Gateway API</dt><dd className="mono">{l.gateway_url}</dd></>}
            <dt>Last data</dt><dd>{ago(l.age_s)}</dd>
            {l.mode === "pull" && <><dt>Polls</dt><dd className="mono">{l.polls} · {l.failures} failed</dd></>}
            {l.error && <><dt>Last error</dt><dd style={{ color: "var(--ember)" }}>{l.error}</dd></>}
          </dl>
        </Card>
        <Card title="Gateway" sub={g.id != null ? `id ${g.id}` : undefined} id="h-gw">
          <div className="kv" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <div><div className="k">Frames received</div><div className="v">{g.stats.rx ?? 0}</div></div>
            <div><div className="k">Bad / duplicate</div><div className="v">{g.stats.bad ?? 0} / {g.stats.dup ?? 0}</div></div>
            <div><div className="k">Bridge emergency SMS</div><div className="v">{g.stats.emergency ?? 0}</div></div>
            <div><div className="k">Outbox pending</div><div className="v">{g.outbox_pending}</div></div>
          </div>
          <p className="note" style={{ marginBottom: 0 }}>Fire episode: <b>{g.episode ?? "none"}</b> · bridge {g.bridge ? "reporting" : "not reporting (no serial link in this setup)"}</p>
        </Card>
        <Card title="Models on the gateway" id="h-models">
          {!Object.keys(models).length ? <Empty>No model status.</Empty> : (
            <dl className="kv-list">
              {Object.entries(models).map(([k, v]) => {
                const m = (typeof v === "object" && v ? v : { state: String(v) }) as { state?: string; detail?: string };
                const tone = m.state === "ok" ? "lv-0" : m.state === "disabled" || m.state === "placeholder" ? "lv-4" : "lv-2";
                return (
                  <Fragment key={k}>
                    <dt>{k.replace(/_/g, " ")}</dt>
                    <dd><span className={`badge lv ${tone}`}>{m.state === "ok" ? "running" : m.state === "placeholder" ? "next phase" : m.state}</span>
                      {m.detail && <div className="note" style={{ marginTop: 3 }}>{m.detail.length > 110 ? m.detail.slice(0, 110) + "…" : m.detail}</div>}</dd>
                  </Fragment>
                );
              })}
            </dl>
          )}
        </Card>
      </div>

      <div className="row3">
        <Card title="Test SMS" sub="sent by the gateway through its modem" id="h-sms">
          <form className="form-row" onSubmit={(e) => { e.preventDefault(); run(api.testSms(sms), "Test SMS"); }}>
            <div className="field"><label htmlFor="sms">Text</label><input id="sms" value={sms} maxLength={140} onChange={(e) => setSms(e.target.value)} /></div>
            <button className="btn primary">Send</button>
          </form>
        </Card>
        <Card title="Test email" sub={config?.smtp ? "SMTP configured" : "no SMTP: emails are recorded as logged"} id="h-mail">
          <form className="form-row" onSubmit={(e) => { e.preventDefault(); if (to) run(api.testEmail(to), "Test email"); }}>
            <div className="field"><label htmlFor="to">Recipient</label><input id="to" type="email" required placeholder="operator@example.org" value={to} onChange={(e) => setTo(e.target.value)} /></div>
            <button className="btn primary">Send</button>
          </form>
        </Card>
        <Card title="Operator access" sub={config?.operator_token_required ? "a token is required for actions" : "actions open (demo setup)"} id="h-tok">
          <form className="form-row" onSubmit={(e) => { e.preventDefault(); setOperatorToken(tok); toast({ tone: "ok", title: tok ? "Operator token saved in this browser" : "Operator token cleared" }); }}>
            <div className="field"><label htmlFor="tok">Operator token</label><input id="tok" type="password" autoComplete="off" value={tok} onChange={(e) => setTok(e.target.value)} /></div>
            <button className="btn">Save</button>
          </form>
        </Card>
      </div>

      <div className="row2">
        <Card title="Emails" sub="alert emails received from the gateway" flush id="h-emails">
          {!emails.length ? <Empty>No email yet.</Empty> : (
            <table className="tbl"><thead><tr><th>Time</th><th>To</th><th>Subject</th><th>Status</th></tr></thead>
              <tbody>{emails.slice(0, 12).map((e) => (
                <tr key={e.id}><td className="mono">{stamp(e.t)}</td><td>{e.recipient}</td><td>{e.subject}</td>
                  <td><span className={`badge lv ${e.status === "sent" ? "lv-0" : e.status === "failed" ? "lv-3" : "lv-4"}`}>{e.status}</span></td></tr>
              ))}</tbody></table>
          )}
        </Card>
        <Card title="Operator commands" flush id="h-cmds">
          {!cmds.length ? <Empty>No command yet.</Empty> : (
            <table className="tbl"><thead><tr><th>Time</th><th>Command</th><th>Box</th><th>Status</th></tr></thead>
              <tbody>{cmds.slice(0, 12).map((c) => (
                <tr key={c.id}><td className="mono">{stamp(c.t)}</td><td>{c.name.replace(/_/g, " ")}</td><td className="mono">{String(c.body.box ?? "–")}</td>
                  <td><span className={`badge lv ${c.status === "done" ? "lv-0" : c.status === "sent" ? "lv-5" : "lv-2"}`}>{c.status}</span></td></tr>
              ))}</tbody></table>
          )}
        </Card>
      </div>
    </main>
  );
}
