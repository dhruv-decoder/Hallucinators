"use client";
import clsx from "clsx";
import { useEffect, useState } from "react";

export const cn = (...a: any[]) => clsx(a);

export function Card({ title, desc, children, className }: { title?: string; desc?: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("card", className)}>
      {title && <h3 className="mb-1 text-[15px] font-semibold">{title}</h3>}
      {desc && <p className="mb-3.5 text-[12.5px] text-muted">{desc}</p>}
      {children}
    </div>
  );
}

export function Kpi({ label, value, tone, foot, info }: { label: string; value: React.ReactNode; tone?: "good" | "bad"; foot?: string; info?: string }) {
  return (
    <div className="kpi">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted">
        {label}{info && <span title={info} className="inline-flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-line-2 text-[9px] text-faint">i</span>}
      </div>
      <div className={cn("num mt-1.5 text-2xl font-bold tracking-tight", tone === "good" && "text-pass", tone === "bad" && "text-block")}>{value}</div>
      {foot && <div className="mt-0.5 text-[11px] text-faint">{foot}</div>}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, hint, action }: { icon?: any; title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="empty">
      {Icon && <Icon className="mb-3 text-faint" size={26} />}
      <div className="text-sm font-semibold text-ink">{title}</div>
      {hint && <div className="mx-auto mt-1 max-w-[440px] text-[13px] text-muted">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Badge({ action }: { action: string }) {
  // .badge-<action> classes live in globals.css and adapt to light/dark via color-mix.
  return <span className={cn("badge", `badge-${action}`)}>{action.replace("_", "-")}</span>;
}

export function ProgressBar({ progress, label }: { progress: number; label?: string }) {
  return (
    <div className="mt-3">
      <div className="h-2.5 overflow-hidden rounded-full border border-line bg-[#0c1218]">
        <div className="h-full bg-gradient-to-r from-accent to-[#2b8f99] transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
      {label && <div className="mt-1.5 flex justify-between text-xs text-muted">{label}</div>}
    </div>
  );
}

/* ---- tiny toast store ---- */
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
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col gap-2.5">
      {ts.map((t) => (
        <div key={t.id} className={cn("animate-slidein min-w-[240px] rounded-[10px] border border-line-2 bg-panel-2 px-3.5 py-3 shadow-xl",
          t.kind === "ok" && "border-l-[3px] border-l-pass", t.kind === "err" && "border-l-[3px] border-l-block", !t.kind && "border-l-[3px] border-l-accent")}>
          <div className="font-semibold">{t.title}</div>
          {t.msg && <div className="mt-0.5 text-xs text-muted">{t.msg}</div>}
        </div>
      ))}
    </div>
  );
}
