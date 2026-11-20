import { useEffect, useRef, type ReactNode } from "react";
import type { BoxState, Level } from "../lib/types";
import { LEVEL_LABEL, LEVEL_SHORT, LEVEL_WORD, cap } from "../lib/format";

export function LevelBadge({ level, strong = false, short = false }: { level: Level; strong?: boolean; short?: boolean }) {
  return (
    <span className={`badge lv lv-${level}${strong ? " strong" : ""}`}>
      {short ? `${LEVEL_SHORT[level]} ${LEVEL_WORD[level]}` : LEVEL_LABEL[level]}
    </span>
  );
}

export function StatePill({ state, lost }: { state?: BoxState; lost?: boolean }) {
  const s = lost ? "lost" : state ?? "unknown";
  const label = lost ? "Lost" : s === "unknown" ? "No data" : cap(s);
  return (
    <span className={`state-pill st-${s}`}>
      <span className={`dot${s === "fire" ? " pulse" : ""}`} />
      {label}
    </span>
  );
}

export function Card({ title, sub, right, children, flush, id }: { title: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; flush?: boolean; id?: string }) {
  return (
    <section className="card" aria-labelledby={id}>
      <header className="card-h">
        <h2 id={id}>{title}</h2>
        {sub && <span className="sub">{sub}</span>}
        {right && <div className="right">{right}</div>}
      </header>
      <div className={flush ? "card-b flush" : "card-b"}>{children}</div>
    </section>
  );
}

export function Confirm({ title, body, confirm, tone = "primary", onConfirm, onClose }: {
  title: string; body: ReactNode; confirm: string; tone?: "primary" | "danger"; onConfirm: () => void; onClose: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
        <h2 id="dlg-t">{title}</h2>
        <div className="muted">{body}</div>
        <div className="actions">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button ref={ref} className={`btn ${tone}`} onClick={() => { onConfirm(); onClose(); }}>{confirm}</button>
        </div>
      </div>
    </div>
  );
}

export function Empty({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return <div className="empty">{icon}{children}</div>;
}
