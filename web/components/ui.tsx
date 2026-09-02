"use client";
import clsx from "clsx";
import { useEffect, useState } from "react";

export const cn = (...a: any[]) => clsx(a);

// The source art sits on a white canvas, so it is framed in a white tile and zoomed slightly to crop the
// margins, which makes it read as a crisp app icon on both themes.
export function BrandMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <span className={cn("relative flex-none overflow-hidden rounded-[7px] bg-white ring-1 ring-black/5", className)}
      style={{ width: size, height: size, boxShadow: "var(--glow)" }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="ControlPlane" className="absolute inset-0 h-full w-full object-cover" style={{ transform: "scale(1.28)" }} />
    </span>
  );
}

/**
 * The single container. A card has at most one title, one line of orientation, and one primary action;
 * anything more belongs in a tooltip or a dialog. Holding that line is what keeps a dense product legible.
 */
export function Card({ title, desc, action, children, className }: {
  title?: string; desc?: string; action?: React.ReactNode; children?: React.ReactNode; className?: string;
}) {
  return (
    <section className={cn("card", className)}>
      {(title || action) && (
        <header className={cn("flex items-start gap-3", desc ? "mb-1" : "mb-3.5")}>
          {title && <h3 className="t-h2 min-w-0 flex-1">{title}</h3>}
          {action && <div className="flex flex-none items-center gap-2">{action}</div>}
        </header>
      )}
      {desc && <p className="t-meta prose-w mb-4">{desc}</p>}
      {children}
    </section>
  );
}

export function Kpi({ label, value, tone, foot, info }: {
  label: string; value: React.ReactNode; tone?: "good" | "bad"; foot?: string; info?: string;
}) {
  return (
    <div className="kpi">
      <div className="t-label flex items-center gap-1.5">
        {label}{info && <Info text={info} />}
      </div>
      <div className={cn("num mt-2 text-[22px] font-bold leading-none tracking-tight",
        tone === "good" && "text-pass", tone === "bad" && "text-block")}>{value}</div>
      {foot && <div className="mt-1.5 text-[11.5px] leading-tight text-faint">{foot}</div>}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, hint, action }: {
  icon?: any; title: string; hint?: string; action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      {Icon && <Icon className="mb-3 text-faint" size={26} />}
      <div className="t-h2">{title}</div>
      {hint && <div className="t-meta mx-auto mt-1.5 max-w-[440px]">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Badge({ action }: { action: string }) {
  return <span className={cn("badge", `badge-${action}`)}>{action.replace("_", "-")}</span>;
}

export function ProgressBar({ progress, label }: { progress: number; label?: string }) {
  return (
    <div className="mt-3">
      <div className="h-2 overflow-hidden rounded-full border border-line" style={{ background: "var(--bg-2)" }}>
        <div className="h-full bg-gradient-to-r from-accent to-[#2b8f99] transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
      {label && <div className="t-meta mt-2 flex justify-between">{label}</div>}
    </div>
  );
}

/* ---- explanation affordances ---------------------------------------------------------------- */

/** A small marker that reveals an explanation on hover. Use on any metric, threshold, or piece of jargon. */
export function Info({ text, align = "center" }: { text: string; align?: "center" | "right" }) {
  return (
    <span className={cn("tip", align === "right" && "tip-right")} tabIndex={0} role="note">
      <span className="tip-dot" aria-hidden>i</span>
      <span className="tip-body">{text}</span>
    </span>
  );
}

/** Wraps any element to give it a hover explanation. Pair with `tip-term` to mark the text visually. */
export function Tip({ text, children, align = "center", className }: {
  text: string; children: React.ReactNode; align?: "center" | "right"; className?: string;
}) {
  return (
    <span className={cn("tip", align === "right" && "tip-right", className)} tabIndex={0}>
      {children}
      <span className="tip-body">{text}</span>
    </span>
  );
}

export type LegendItem = { color: string; label: string; value?: React.ReactNode; desc?: string };

/** A colour key where each entry explains what that colour means on hover. */
export function Legend({ items, title, className }: { items: LegendItem[]; title?: string; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-5 gap-y-2", className)}>
      {title && <span className="t-label">{title}</span>}
      {items.map((it) => (
        <Tip key={it.label} text={it.desc ?? it.label}>
          <span className="inline-flex items-center gap-1.5 text-[12px] text-muted">
            {/* The swatch already reads as interactive, so a dashed underline on every entry only adds noise. */}
            <i className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: it.color }} />
            <span className={it.desc ? "cursor-help transition-colors hover:text-ink" : undefined}>{it.label}</span>
            {it.value !== undefined && <b className="num text-ink">{it.value}</b>}
          </span>
        </Tip>
      ))}
    </div>
  );
}

/** A proportional bar with a legend beneath. One component for every action-mix rendering in the app. */
export function StackedBar({ items, total }: { items: LegendItem[]; total: number }) {
  const denom = Math.max(total, 1);
  return (
    <div className="flex h-2.5 overflow-hidden rounded-full border border-line" style={{ background: "var(--bg-2)" }}>
      {items.map((it) => {
        const n = typeof it.value === "number" ? it.value : 0;
        const w = (n / denom) * 100;
        return w > 0 ? <div key={it.label} style={{ width: `${w}%`, background: it.color }} title={`${it.label}: ${n}`} /> : null;
      })}
    </div>
  );
}

/** A centred dialog for long-form reading. Closes on backdrop click or Escape. */
export function Modal({ open, onClose, title, subtitle, children }: {
  open: boolean; onClose: () => void; title: string; subtitle?: string; children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur-[2px]" onClick={onClose} />
      <div role="dialog" aria-modal="true"
        className="fixed left-1/2 top-1/2 z-[90] flex max-h-[88vh] w-[min(880px,94vw)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-line bg-panel shadow-2xl">
        <header className="flex items-start gap-3 border-b border-line px-7 py-5">
          <div className="min-w-0 flex-1">
            <h3 className="t-h1">{title}</h3>
            {subtitle && <p className="t-meta prose-w mt-1.5">{subtitle}</p>}
          </div>
          <button className="btn flex-none" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="overflow-auto px-7 py-6">{children}</div>
      </div>
    </>
  );
}

/* ---- toasts ---- */
type Toast = { id: number; title: string; msg?: string; kind?: "ok" | "err" };
let _toasts: Toast[] = [];
let _subs: ((t: Toast[]) => void)[] = [];
let _id = 0;
export function toast(title: string, msg?: string, kind?: "ok" | "err") {
  const t = { id: ++_id, title, msg, kind };
  _toasts = [..._toasts, t]; _subs.forEach((s) => s(_toasts));
  setTimeout(() => { _toasts = _toasts.filter((x) => x.id !== t.id); _subs.forEach((s) => s(_toasts)); }, 4200);
}
export function Toaster() {
  const [ts, setTs] = useState<Toast[]>([]);
  useEffect(() => { _subs.push(setTs); return () => { _subs = _subs.filter((s) => s !== setTs); }; }, []);
  return (
    <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2.5">
      {ts.map((t) => (
        <div key={t.id} className={cn("animate-slidein min-w-[260px] max-w-[360px] rounded-[10px] border border-line-2 bg-panel-2 px-4 py-3 shadow-xl",
          t.kind === "ok" && "border-l-[3px] border-l-pass", t.kind === "err" && "border-l-[3px] border-l-block", !t.kind && "border-l-[3px] border-l-accent")}>
          <div className="t-h2">{t.title}</div>
          {t.msg && <div className="t-meta mt-1">{t.msg}</div>}
        </div>
      ))}
    </div>
  );
}
