"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity, Crosshair, Cpu, Gauge, History, Info, LayoutGrid, LifeBuoy, MousePointerClick, Play,
  Rss, ScrollText, SlidersHorizontal, Sparkles, Wallet, Workflow, X,
} from "lucide-react";
import { Action, AgentReceipt, api, ControlRow, GeneratedPolicy, Receipt, RuntimeObservability, Scenario, Summary, UseCaseSpec } from "@/lib/api";
import { ACTION_COLOR, AXIS_COLOR, fmtEta, usd, worstAxis } from "@/lib/format";
import { Badge, Card, Kpi, ProgressBar, toast, Toaster } from "./ui";
import { QuadrantChart, Sparkline } from "./charts";
import { ThemeToggle } from "./theme";

type View = "configure" | "overview" | "feed" | "quadrant" | "pnl" | "benchmark" | "runtime" | "replay" | "agents" | "compliance" | "detectors" | "help";
const NAV: { group: string; items: { id: View; label: string; icon: any }[] }[] = [
  { group: "Set up", items: [
    { id: "configure", label: "Use-case setup", icon: SlidersHorizontal } ] },
  { group: "Monitor", items: [
    { id: "overview", label: "Overview", icon: LayoutGrid }, { id: "feed", label: "Live feed", icon: Rss },
    { id: "quadrant", label: "Confidently-wrong", icon: Crosshair }, { id: "pnl", label: "Oversight P&L", icon: Wallet } ] },
  { group: "Prove", items: [
    { id: "benchmark", label: "Latency & scale", icon: Gauge }, { id: "runtime", label: "Runtime health", icon: Activity }, { id: "replay", label: "What-If replay", icon: History },
    { id: "agents", label: "Agent oversight", icon: Workflow } ] },
  { group: "Govern", items: [
    { id: "compliance", label: "Compliance", icon: ScrollText }, { id: "detectors", label: "Detectors & models", icon: Cpu },
    { id: "help", label: "Getting started", icon: LifeBuoy } ] },
];
const TITLES: Record<View, [string, string]> = {
  configure: ["Configure for your use case", "Tune oversight to your traffic, latency, risk, and data — the policy is generated for you"],
  overview: ["Overview", "One verdict across performance, cost, and responsibility — in real time"],
  feed: ["Live feed", "Every decision, as it happens — the audit trail behind each response"],
  quadrant: ["Confidently-wrong map", "The danger zone we exist to catch: sure of itself and wrong"],
  pnl: ["Oversight P&L", "Safer AND cheaper — a negative price tag, measured not asserted"],
  benchmark: ["Latency & scale", "Does oversight slow the model down? Measure it."],
  runtime: ["Runtime health", "Live service telemetry, saturation protection, and detector cost"],
  replay: ["What-If replay", "Re-run the same workload under different risk appetites — the proof engine"],
  agents: ["Agent oversight", "Catching compounding risk across a multi-step agent"],
  compliance: ["Compliance", "Receipts → EU AI Act / ISO 42001 / NIST AI RMF evidence"],
  detectors: ["Detectors & models", "The tiered stack: cheap first, model on the tail"],
  help: ["Getting started", "What this is and how to read it"],
};
export default function Dashboard({ onHome }: { onHome?: () => void }) {
  const [view, setView] = useState<View>("overview");
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [net, setNet] = useState<number[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [drawer, setDrawer] = useState<Receipt | null>(null);
  const ids = useRef<Set<string>>(new Set());

  const addReceipt = useCallback((r: Receipt) => {
    if (ids.current.has(r.request_id)) return;
    ids.current.add(r.request_id);
    setReceipts((prev) => [r, ...prev].slice(0, 300));
    setNet((prev) => [...prev, (prev.at(-1) ?? 0) + r.pnl.net_usd].slice(-400));
  }, []);

  useEffect(() => {
    api.summary().then(setSummary).catch(() => {});
    api.receipts(80).then((d) => d.receipts.slice().reverse().forEach(addReceipt)).catch(() => {});
    let es: EventSource | null = null;
    const connect = () => {
      es = new EventSource(api.streamUrl());
      es.onmessage = (e) => {
        if (e.data.startsWith(":")) return;
        const m = JSON.parse(e.data);
        if (m.type === "receipt") addReceipt(m.receipt);
        else if (m.type === "summary") setSummary(m.summary);
      };
      es.onerror = () => { es?.close(); setTimeout(connect, 2000); };
    };
    connect();
    return () => es?.close();
  }, [addReceipt]);

  const [busy, setBusy] = useState(false);
  const sendTraffic = async () => {
    setBusy(true);
    try { await api.simulate(); toast("Demo traffic sent", "9 requests overseen", "ok"); }
    catch (e) { toast("Failed", String(e), "err"); }
    setBusy(false);
  };

  const [guide, setGuide] = useState(false);
  useEffect(() => { try { setGuide(localStorage.getItem("cp-guide") !== "seen"); } catch {} }, []);
  const dismissGuide = () => { setGuide(false); try { localStorage.setItem("cp-guide", "seen"); } catch {} };

  const incidents = (summary?.by_action?.block ?? 0) + (summary?.by_action?.escalate ?? 0);

  return (
    <div className="grid min-h-screen grid-cols-[232px_1fr] max-lg:grid-cols-[64px_1fr]">
      {/* sidebar */}
      <aside className="sticky top-0 flex h-screen flex-col gap-1 overflow-auto border-r border-line bg-bg-2 p-3">
        <button onClick={onHome} title="Back to home" className="flex items-center gap-2.5 px-2.5 pb-4 pt-1.5 text-left">
          <div className="relative h-7 w-7 flex-none rounded-[7px]" style={{ background: "linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #0a3))", boxShadow: "var(--glow)" }}>
            <div className="absolute inset-2 rounded-[3px] border-2" style={{ borderColor: "color-mix(in srgb, var(--accent-ink) 55%, transparent)" }} />
          </div>
          <div className="max-lg:hidden"><b className="text-sm">ControlPlane</b><small className="block text-[11px] text-faint">The Tower</small></div>
        </button>
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="px-3 pb-1.5 pt-3.5 text-[10px] uppercase tracking-wider text-faint max-lg:hidden">{g.group}</div>
            {g.items.map((it) => {
              const Icon = it.icon;
              return (
                <div key={it.id} onClick={() => setView(it.id)} className={`navitem ${view === it.id ? "navitem-active" : ""}`}>
                  <Icon size={16} className="opacity-90" /><span className="max-lg:hidden">{it.label}</span>
                  {it.id === "feed" && incidents > 0 && <span className="ml-auto rounded-full bg-block px-1.5 text-[10px] font-bold text-[#180a0a] max-lg:hidden">{incidents}</span>}
                </div>
              );
            })}
          </div>
        ))}
        <div className="flex-1" />
        <div className="border-t border-line px-3 py-2.5 text-[11px] text-faint max-lg:hidden">
          <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${summary?.chain_valid ? "bg-pass" : "bg-block"}`} />
          chain {summary?.chain_valid ? "verified" : "—"} · {summary?.requests ?? 0} decisions
        </div>
      </aside>

      {/* main */}
      <div className="flex min-w-0 flex-col">
        <header className="glass sticky top-0 z-10 flex items-center gap-2.5 border-b border-line px-6 py-3">
          <div>
            <div className="text-[15px] font-semibold">{TITLES[view][0]}</div>
            <div className="text-xs text-faint">{TITLES[view][1]}</div>
          </div>
          <span className="flex-1" />
          <span className="pill max-md:hidden" title="Which detectors are model-backed vs heuristic">
            models <b className="text-ink">{summary?.models?.groundedness ?? "—"} · judge:{summary?.models?.judge ?? "off"}</b>
          </span>
          <ThemeToggle />
          {summary && (
            <select className="btn" value={summary.active_policy}
              onChange={(e) => { const k = Object.entries(summary.policies).find(([, v]) => v === e.target.value)?.[0]; if (k) api.setPolicy(k).then(() => toast("Policy switched", e.target.value, "ok")); }}>
              {Object.values(summary.policies).map((p) => <option key={p}>{p}</option>)}
            </select>
          )}
          <button className="btn-primary inline-flex items-center gap-1.5" disabled={busy} onClick={sendTraffic}
            title="Runs 9 realistic requests through the oversight engine so the dashboard fills with live decisions">
            <Play size={14} />{busy ? "running…" : "Send demo traffic"}
          </button>
        </header>

        <main className="mx-auto w-full max-w-[1480px] p-6">
          {guide && <Onboard onDismiss={dismissGuide} onSend={sendTraffic} busy={busy} />}
          <div key={view} className="viewfade">
            {view === "configure" && <Configurator onApplied={() => { api.summary().then(setSummary); setView("overview"); }} />}
            {view === "overview" && <Overview summary={summary} net={net} receipts={receipts} onOpen={setDrawer} onSend={sendTraffic} busy={busy} />}
            {view === "feed" && <Feed receipts={receipts} onOpen={setDrawer} />}
            {view === "quadrant" && <Quadrant receipts={receipts} />}
            {view === "pnl" && <PnlView summary={summary} net={net} />}
            {view === "benchmark" && <Benchmark />}
            {view === "runtime" && <RuntimeHealth />}
            {view === "replay" && <Replay />}
            {view === "agents" && <Agents />}
            {view === "compliance" && <Compliance />}
            {view === "detectors" && <Detectors summary={summary} />}
            {view === "help" && <Help />}
          </div>
          <footer className="mt-10 flex items-center justify-between border-t border-line pt-5 text-xs text-faint max-md:flex-col max-md:gap-2">
            <span>ControlPlane · The Tower — value-of-information oversight</span>
            <span>{summary?.requests ?? 0} decisions · chain {summary?.chain_valid ? "verified" : "—"} · {summary?.models?.judge && summary.models.judge !== "disabled" ? `judge:${summary.models.judge}` : "heuristics"}</span>
          </footer>
        </main>
      </div>

      {drawer && <ReceiptDrawer receipt={drawer} onClose={() => setDrawer(null)} />}
      <Toaster />
    </div>
  );
}

/* ---- feed row ---- */
function FeedRow({ r, onOpen }: { r: Receipt; onOpen: (r: Receipt) => void }) {
  const [ax, p] = worstAxis(r);
  return (
    <div onClick={() => onOpen(r)} className="grid cursor-pointer grid-cols-[86px_1fr_auto] items-center gap-3 rounded-[10px] border border-line bg-panel-2 px-3 py-2.5 transition hover:translate-x-0.5 hover:border-accent">
      <Badge action={r.action} />
      <div className="min-w-0">
        <div className="truncate">{(r.use_case || "").replace("_", " ")} · {ax || "—"} <span className="num">{p.toFixed(2)}</span></div>
        <div className="truncate font-mono text-[11px] text-faint">{r.request_id} · {r.stopping_reason}</div>
      </div>
      <div className={`num text-xs ${r.pnl.net_usd < 0 ? "text-pass" : "text-muted"}`}>{usd(r.pnl.net_usd)}</div>
    </div>
  );
}

/* ---- views ---- */
function Field({ label, value, opts, onChange, hint }: { label: string; value: string; opts: [string, string][]; onChange: (v: string) => void; hint?: string }) {
  return (
    <label className="block">
      <div className="mb-1 text-[12px] font-medium text-muted">{label}{hint && <span className="ml-1 text-faint">· {hint}</span>}</div>
      <div className="flex flex-wrap gap-1.5">
        {opts.map(([v, l]) => (
          <button key={v} onClick={() => onChange(v)} className={`rounded-lg border px-2.5 py-1.5 text-[13px] transition ${value === v ? "border-accent bg-accent-dim text-ink" : "border-line text-muted hover:border-line-2 hover:text-ink"}`}>{l}</button>
        ))}
      </div>
    </label>
  );
}

function Configurator({ onApplied }: { onApplied: () => void }) {
  const [spec, setSpec] = useState<UseCaseSpec>({ use_case: "customer_support", weekly_volume: 50000, latency_budget: "interactive", risk_tolerance: "medium", data_sensitivity: "internal", geo: "EU" });
  const [res, setRes] = useState<GeneratedPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof UseCaseSpec) => (v: string) => setSpec((s) => ({ ...s, [k]: v }));

  const gen = async (apply: boolean) => {
    setBusy(true);
    try {
      const r = await api.generatePolicy(spec, apply);
      setRes(r);
      if (apply) { toast("Policy applied", `${r.profile_id} is now live`, "ok"); onApplied(); }
    } catch (e) { toast("Failed", String(e), "err"); }
    setBusy(false);
  };
  const proj = res?.projection;

  return (
    <div className="grid grid-cols-[380px_1fr] gap-4 max-lg:grid-cols-1">
      <Card title="Describe your use case" desc="ControlPlane maps these business facts to the value-of-information knobs — no manual tuning.">
        <div className="flex flex-col gap-3.5">
          <Field label="Use case" value={spec.use_case} onChange={set("use_case")} opts={[["customer_support", "Support bot"], ["internal_copilot", "Internal copilot"], ["decision_support", "Decision support"], ["agentic", "Agentic workflow"]]} />
          <Field label="Latency budget" value={spec.latency_budget} onChange={set("latency_budget")} hint="how fast must it respond" opts={[["realtime", "Real-time"], ["interactive", "Interactive"], ["batch", "Batch"]]} />
          <Field label="Risk tolerance" value={spec.risk_tolerance} onChange={set("risk_tolerance")} hint="cost of a wrong answer" opts={[["low", "Low (verify hard)"], ["medium", "Medium"], ["high", "High (trust more)"]]} />
          <Field label="Data sensitivity" value={spec.data_sensitivity} onChange={set("data_sensitivity")} opts={[["public", "Public"], ["internal", "Internal"], ["regulated", "Regulated"]]} />
          <Field label="Geography" value={spec.geo} onChange={set("geo")} opts={[["EU", "EU"], ["US", "US"], ["IN", "India"], ["global", "Global"]]} />
          <label className="block">
            <div className="mb-1 text-[12px] font-medium text-muted">Weekly volume · <span className="num text-ink">{spec.weekly_volume.toLocaleString()}</span> interactions</div>
            <input type="range" min={5000} max={500000} step={5000} value={spec.weekly_volume} onChange={(e) => setSpec((s) => ({ ...s, weekly_volume: +e.target.value }))} className="w-full accent-[color:var(--accent)]" />
          </label>
          <button className="btn-primary" disabled={busy} onClick={() => gen(false)}>{busy ? "generating…" : "Generate policy"}</button>
        </div>
      </Card>

      {res && proj ? (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2">
            <Kpi label="Cleared @ T0" value={`${proj.cleared_at_t0_pct}%`} foot="free tier" />
            <Kpi label="Added latency p95" value={`${proj.added_latency_p95_ms} ms`} foot="projected" />
            <Kpi label="Escalations" value={`${(proj.escalation_rate * 100).toFixed(0)}%`} foot={`${proj.human_reviews_per_month.toLocaleString()}/mo to humans`} />
            <Kpi label="Projected net / mo" value={usd(proj.projected_monthly_net_usd)} tone={proj.self_funding ? "good" : "bad"} foot={proj.self_funding ? "self-funding" : ""} />
          </div>
          <Card title={`Generated policy · ${res.profile_id}`} desc="Why each knob is set the way it is — the mapping is legible, not a black box.">
            <div className="mb-3 grid grid-cols-2 gap-2 text-[13px] max-md:grid-cols-1">
              {res.rationale.map((r, i) => <div key={i} className="rounded-lg border border-line bg-panel-2 px-3 py-2 text-muted">{r}</div>)}
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="text-[12px] text-faint">detectors:</span>
              {res.recommended_detectors.map((d) => <span key={d} className="rounded-md border border-line bg-panel px-1.5 py-0.5 text-[11px] text-muted">{d}</span>)}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="text-[12px] text-faint">compliance:</span>
              {res.compliance.map((c) => <span key={c} className="rounded-md border border-line bg-accent-dim px-1.5 py-0.5 text-[11px]" style={{ color: "var(--accent)" }}>{c}</span>)}
            </div>
            <button className="btn-primary mt-4" disabled={busy} onClick={() => gen(true)}>Apply this policy live →</button>
            <p className="mt-2 text-xs text-faint">{proj.note}</p>
          </Card>
        </div>
      ) : (
        <div className="flex items-center justify-center rounded-xl border border-dashed border-line text-center">
          <div className="p-10 text-faint"><SlidersHorizontal className="mx-auto mb-2" /> Describe your use case, then <b className="text-muted">Generate policy</b> to see the tuned knobs, a projection, and the reasoning.</div>
        </div>
      )}
    </div>
  );
}

function Onboard({ onDismiss, onSend, busy }: { onDismiss: () => void; onSend: () => void; busy: boolean }) {
  const steps = [
    { icon: Play, t: "Send demo traffic", d: "populate the tower with real overseen requests" },
    { icon: MousePointerClick, t: "Open any decision", d: "see its verdict and value-of-information trace" },
    { icon: Sparkles, t: "Explore the panels", d: "P&L, latency, agents, compliance — each has a Run button" },
  ];
  return (
    <div className="mb-4 flex items-center gap-4 rounded-xl border border-line bg-panel px-4 py-3 max-md:flex-col max-md:items-start" style={{ boxShadow: "var(--shadow)" }}>
      <div className="flex items-center gap-2 whitespace-nowrap font-semibold"><Sparkles size={16} style={{ color: "var(--accent)" }} /> You&rsquo;re in the live app</div>
      <div className="flex flex-1 flex-wrap items-center gap-x-5 gap-y-1">
        {steps.map((s, i) => { const Icon = s.icon; return (
          <span key={s.t} className="inline-flex items-center gap-1.5 text-[13px] text-muted">
            <span className="num text-faint">{i + 1}</span><Icon size={13} style={{ color: "var(--accent)" }} />
            <b className="text-ink">{s.t}</b> — {s.d}
          </span>
        ); })}
      </div>
      <button className="btn-primary inline-flex items-center gap-1.5 whitespace-nowrap" disabled={busy} onClick={onSend}><Play size={13} />Try it</button>
      <button className="btn" onClick={onDismiss} title="Dismiss"><X size={14} /></button>
    </div>
  );
}

function GetStarted({ onSend, busy }: { onSend: () => void; busy: boolean }) {
  const steps = [
    { n: "1", t: "Send demo traffic", d: "Nine realistic support/agent requests run through the value-of-information cascade — most clear instantly, a few climb to a model or a human." },
    { n: "2", t: "Watch the P&L go negative", d: "Cost-axis savings (route-downs, cache) pay for the safety checks — oversight with a negative price tag." },
    { n: "3", t: "Drill into any decision", d: "Every response has a signed receipt: the per-axis verdict, which checks ran and why, and the action taken." },
  ];
  return (
    <div className="mx-auto max-w-[860px]">
      <div className="card flex flex-col items-center gap-3 py-12 text-center" style={{ background: "radial-gradient(700px 220px at 50% -10%, var(--accent-dim), var(--grad-1))" }}>
        <div className="flex h-12 w-12 items-center justify-center rounded-xl" style={{ background: "var(--accent-dim)", color: "var(--accent)" }}><Play size={22} /></div>
        <h2 className="text-2xl font-semibold tracking-tight">Start the live tower</h2>
        <p className="max-w-[520px] text-muted">This is the real oversight engine — nothing is pre-computed. Send a burst of demo traffic and the dashboard fills with live decisions you can inspect.</p>
        <button className="btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-[15px]" disabled={busy} onClick={onSend}><Play size={16} />{busy ? "running…" : "Send demo traffic"}</button>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 max-md:grid-cols-1">
        {steps.map((s) => (
          <div key={s.n} className="card">
            <div className="num mb-1.5 text-sm font-semibold" style={{ color: "var(--accent)" }}>{s.n}</div>
            <h3 className="font-semibold">{s.t}</h3>
            <p className="mt-1 text-[13px] text-muted">{s.d}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 flex items-center justify-center gap-1.5 text-center text-xs text-faint"><Info size={12} /> Everything is real and reproducible — see the <b className="text-muted">Getting started</b> panel for the one-line integration.</p>
    </div>
  );
}

function Overview({ summary, net, receipts, onOpen, onSend, busy }: { summary: Summary | null; net: number[]; receipts: Receipt[]; onOpen: (r: Receipt) => void; onSend: () => void; busy: boolean }) {
  const s = summary;
  if (receipts.length === 0) return <GetStarted onSend={onSend} busy={busy} />;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-6 gap-3 max-xl:grid-cols-3">
        <Kpi label="Decisions" value={s?.requests ?? 0} foot="overseen inline" />
        <Kpi label="Net P&L" value={usd(s?.net_usd ?? 0)} tone={(s?.net_usd ?? 0) < 0 ? "good" : "bad"} foot={(s?.net_usd ?? 0) < 0 ? "self-funding" : "safety > savings"} info="Safety spend minus cost saved. Negative = oversight pays for itself." />
        <Kpi label="Cleared @ T0" value={`${s?.cleared_at_t0_pct ?? 100}%`} foot="free tier, ~0ms" info="Share resolved by free checks — the fast path." />
        <Kpi label="Scrutiny" value={`${(s?.scrutiny ?? 1).toFixed(2)}×`} foot="adaptive thermostat" info="Auto-scales verification with recent risk." />
        <Kpi label="Escalations" value={s?.by_action?.escalate ?? 0} foot="to a human" />
        <Kpi label="Blocks" value={s?.by_action?.block ?? 0} foot="unsafe / leaks" />
      </div>
      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        <Card title="Cumulative oversight P&L" desc="Every point is a decision; below zero means the cost-axis savings are paying for the safety checks."><Sparkline series={net} /></Card>
        <Card title="Recent decisions" desc="Newest first — click any row for the full receipt.">
          <div className="flex max-h-[250px] flex-col gap-2 overflow-auto">
            {receipts.length ? receipts.slice(0, 12).map((r) => <FeedRow key={r.request_id} r={r} onOpen={onOpen} />)
              : <div className="rounded-xl border border-dashed border-line p-10 text-center text-faint">No traffic yet — click “Send demo traffic”.</div>}
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-[1.3fr_1fr] gap-4 max-lg:grid-cols-1">
        <Card title="Action mix" desc="How verdicts split across the fleet — most pass, the tail is repaired, escalated, or blocked.">
          {(() => {
            const ba = s?.by_action ?? {}; const total = Object.values(ba).reduce((a, b) => a + b, 0) || 1;
            const order: Action[] = ["pass", "annotate", "auto_repair", "escalate", "block"];
            return (<>
              <div className="flex h-3 overflow-hidden rounded-full border border-line">
                {order.map((a) => { const w = (ba[a] ?? 0) / total * 100; return w > 0 ? <div key={a} style={{ width: `${w}%`, background: ACTION_COLOR[a] }} title={`${a}: ${ba[a]}`} /> : null; })}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
                {order.map((a) => <span key={a} className="inline-flex items-center gap-1.5 text-muted"><i className="h-2.5 w-2.5 rounded-full" style={{ background: ACTION_COLOR[a] }} />{a.replace("_", "-")} <b className="num text-ink">{ba[a] ?? 0}</b></span>)}
              </div>
            </>);
          })()}
        </Card>
        <Card title="System status">
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px]">
            <span className="text-muted">active policy</span><span className="num truncate">{s?.active_policy ?? "—"}</span>
            <span className="text-muted">groundedness</span><span>{s?.models?.groundedness ?? "—"}</span>
            <span className="text-muted">safety · judge</span><span>{s?.models?.safety ?? "heuristic"} · {s?.models?.judge ?? "off"}</span>
            <span className="text-muted">audit chain</span><span style={{ color: s?.chain_valid ? "var(--pass)" : "var(--block)" }}>{s?.chain_valid ? "verified ✓" : "—"}</span>
          </div>
        </Card>
      </div>
      <div className="rounded-xl border border-dashed border-line-2 bg-bg-2 p-4">
        <h4 className="mb-2 text-[13px] text-accent">What am I looking at?</h4>
        <p className="text-sm text-muted">ControlPlane sits in front of any model. For every response it decides <b className="text-ink">how much verification that response is worth</b> — buying the cheapest signal that could change the decision first, and letting cost-axis savings pay for the safety checks. Most responses clear instantly at the free tier; only the uncertain, high-stakes tail climbs to costly checks or a human. New here? Open <b className="text-ink">Getting started</b>.</p>
      </div>
    </div>
  );
}

function Feed({ receipts, onOpen }: { receipts: Receipt[]; onOpen: (r: Receipt) => void }) {
  const [f, setF] = useState("");
  const rows = receipts.filter((r) => !f || r.action === f);
  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <select className="btn" value={f} onChange={(e) => setF(e.target.value)}>
          <option value="">all actions</option>{["pass", "annotate", "auto_repair", "escalate", "block"].map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <span className="flex-1" /><span className="text-sm text-muted">click a row for the receipt</span>
      </div>
      <div className="flex flex-col gap-2">
        {rows.length ? rows.slice(0, 200).map((r) => <FeedRow key={r.request_id} r={r} onOpen={onOpen} />)
          : <div className="rounded-xl border border-dashed border-line p-10 text-center text-faint">Nothing yet.</div>}
      </div>
    </Card>
  );
}

function Quadrant({ receipts }: { receipts: Receipt[] }) {
  return (
    <Card desc="Each dot is a response, placed by estimated correctness (x) and model confidence (y), coloured by action. The shaded top-left — high confidence, low correctness — is where hallucinations do damage.">
      <QuadrantChart receipts={receipts} />
      <div className="mt-2 flex flex-wrap gap-3.5 text-[11px] text-muted">
        {Object.entries(ACTION_COLOR).map(([k, c]) => <span key={k} className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{k.replace("_", "-")}</span>)}
      </div>
    </Card>
  );
}

function PnlView({ summary, net }: { summary: Summary | null; net: number[] }) {
  const s = summary;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3">
        <Kpi label="Cost saved" value={usd(s?.cost_saved_usd ?? 0)} tone="good" foot="route-down + cache" />
        <Kpi label="Safety spend" value={usd(s?.safety_spend_usd ?? 0)} foot="checks that ran" />
        <Kpi label="Net" value={usd(s?.net_usd ?? 0)} tone={(s?.net_usd ?? 0) < 0 ? "good" : "bad"} foot={(s?.net_usd ?? 0) < 0 ? "self-funding" : ""} />
      </div>
      <Card title="Cumulative net"><Sparkline series={net} /></Card>
      <div className="rounded-xl border border-dashed border-line-2 bg-bg-2 p-4">
        <h4 className="mb-2 text-[13px] text-accent">Why can oversight be cheaper than nothing?</h4>
        <p className="text-sm text-muted">The same layer that catches errors also finds cheaper paths to the same answer — routing an easy question to a small model, serving a repeat from cache. Those savings are booked against what the safety checks cost. When savings win, the net goes negative: safety <i>and</i> a lower bill. Prices are sourced (docs/EVIDENCE.md).</p>
      </div>
    </div>
  );
}

function useJob() {
  const [prog, setProg] = useState<{ on: boolean; p: number; label: string }>({ on: false, p: 0, label: "" });
  const run = async (start: () => Promise<{ id: string }>, onDone: (r: any) => void) => {
    setProg({ on: true, p: 0, label: "starting…" });
    try {
      const j = await start(); let s = await api.job(j.id);
      while (s.status === "running") {
        await new Promise((r) => setTimeout(r, 350)); s = await api.job(j.id);
        setProg({ on: true, p: s.progress, label: `${s.message} · ${Math.round(s.progress * 100)}% · ETA ${fmtEta(s.eta_seconds)}` });
      }
      if (s.status === "error") toast("Job failed", s.error ?? "", "err");
      else { setProg({ on: true, p: 1, label: `done in ${s.elapsed_seconds}s` }); onDone(s.result); }
    } catch (e) { toast("Job failed", String(e), "err"); setProg({ on: false, p: 0, label: "" }); }
  };
  return { prog, run };
}

function RuntimeHealth() {
  const [obs, setObs] = useState<RuntimeObservability | null>(null);
  const [probeRes, setProbeRes] = useState<any>(null);
  const [probing, setProbing] = useState(false);
  const [ready, setReady] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const [o, r] = await Promise.all([api.observability(), api.ready()]);
        if (live) { setObs(o); setReady(r.ready); }
      } catch { if (live) setReady(false); }
    };
    load();
    const id = setInterval(load, 2000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const runProbe = async () => {
    setProbing(true);
    try {
      const start = await api.runtimeProbe(120, 16);
      let s = await api.job(start.id);
      while (s.status === "running") {
        await new Promise((r) => setTimeout(r, 300));
        s = await api.job(start.id);
      }
      if (s.status === "done") { setProbeRes(s.result); toast("Runtime probe complete", `${s.result.throughput_rps} rps · p95 ${s.result.latency_ms.p95} ms`, "ok"); }
      else toast("Probe failed", s.error ?? "", "err");
    } catch (e) { toast("Probe failed", String(e), "err"); }
    setProbing(false);
  };
  const p = obs?.latency_ms;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-4 gap-3 max-xl:grid-cols-2">
        <Kpi label="p95 oversight" value={`${p?.p95 ?? "—"} ms`} tone="good" foot={`${p?.sample_count ?? 0} samples`} />
        <Kpi label="throughput" value={`${(obs?.throughput_rps ?? 0).toFixed(2)} rps`} foot={`${obs?.active_requests ?? 0} active`} />
        <Kpi label="overload shed" value={`${obs?.overload_rejections ?? 0}`} foot={`max concurrency ${obs?.max_concurrency ?? 0}`} />
        <Kpi label="stream aborts" value={`${obs?.stream_aborts ?? 0}`} foot={`${obs?.errors ?? 0} errors`} />
      </div>
      <Card title="Service readiness" desc="A real liveness/readiness check, plus bounded concurrency so the oversight layer protects itself under load.">
        <div className="flex flex-wrap items-center gap-3">
          <span className={`badge ${ready ? "badge-pass" : "badge-block"}`}>{ready ? "ready" : "not ready"}</span>
          <span className="text-sm text-muted">max concurrency {obs?.config.max_concurrency ?? "—"} · queue timeout {obs?.config.queue_timeout_ms ?? "—"} ms · upstream timeout {obs?.config.upstream_timeout_s ?? "—"} s</span>
          <button className="btn-primary ml-auto" onClick={runProbe} disabled={probing}>{probing ? "running…" : "Run concurrency probe"}</button>
        </div>
      </Card>
      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        <Card title="Tier activity" desc="Counts are based on detector signals recorded during live traffic.">
          <div className="grid grid-cols-3 gap-3">{["T0", "T1", "T2"].map((t) => <Kpi key={t} label={t} value={`${obs?.tier_counts?.[t] ?? 0}`} />)}</div>
        </Card>
        <Card title="Detector latency" desc="Average detector runtime from the live receipt stream.">
          <div className="flex flex-col gap-2">{Object.entries(obs?.detector_avg_latency_ms ?? {}).slice(0, 8).map(([name, ms]) => (
            <div key={name} className="flex items-center justify-between border-b border-line pb-1.5 text-sm"><span className="text-muted">{name}</span><span className="num">{ms.toFixed(2)} ms</span></div>
          ))}{!obs?.detector_avg_latency_ms || Object.keys(obs.detector_avg_latency_ms).length === 0 ? <span className="text-sm text-faint">Run traffic to populate detector telemetry.</span> : null}</div>
        </Card>
      </div>
      {probeRes && <Card title="Concurrency probe" desc="Same real pipeline, driven at bounded concurrency. This is measured runtime behavior, not a capacity claim from the UI.">
        <div className="grid grid-cols-5 gap-3 max-lg:grid-cols-2">
          <Kpi label="requests" value={probeRes.requests} /><Kpi label="concurrency" value={probeRes.concurrency} /><Kpi label="throughput" value={`${probeRes.throughput_rps} rps`} /><Kpi label="p50" value={`${probeRes.latency_ms.p50} ms`} /><Kpi label="p95" value={`${probeRes.latency_ms.p95} ms`} />
        </div>
      </Card>}
    </div>
  );
}

function Benchmark() {
  const [n, setN] = useState(2000), [w, setW] = useState(50000), [res, setRes] = useState<any>(null);
  const { prog, run } = useJob();
  return (
    <Card title="Latency / throughput benchmark" desc="Runs N requests through the local cascade and measures the wall-clock oversight adds per request (the model call is excluded). The T2 judge is off here — it fires only on the uncertain tail.">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-muted">requests</label>
        <select className="btn" value={n} onChange={(e) => setN(+e.target.value)}>{[1000, 2000, 5000].map((x) => <option key={x}>{x}</option>)}</select>
        <label className="text-sm text-muted">weekly volume</label>
        <select className="btn" value={w} onChange={(e) => setW(+e.target.value)}>{[10000, 50000, 250000].map((x) => <option key={x}>{x}</option>)}</select>
        <button className="btn-primary" onClick={() => run(() => api.startBenchmark(n, w), (r) => { setRes(r); toast("Benchmark complete", `p95 ${r.added_latency_ms.p95}ms · ${r.throughput_rps} rps`, "ok"); })}>Run benchmark</button>
      </div>
      {prog.on && <ProgressBar progress={prog.p} label={prog.label} />}
      {res && (
        <div className="mt-4">
          <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2">
            <Kpi label="p50 added" value={`${res.added_latency_ms.p50} ms`} tone="good" />
            <Kpi label="p95 added" value={`${res.added_latency_ms.p95} ms`} tone="good" />
            <Kpi label="p99 added" value={`${res.added_latency_ms.p99} ms`} />
            <Kpi label="throughput" value={`${res.throughput_rps.toLocaleString()} rps`} />
          </div>
          <div className="mt-3.5 grid grid-cols-2 gap-4 max-lg:grid-cols-1">
            <Card title="At enterprise scale" desc="Extrapolated from measured per-request economics — simulated traffic at sourced prices, not billing.">
              <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <span className="text-muted">weekly volume</span><span className="num">{res.at_scale.weekly_volume.toLocaleString()}</span>
                <span className="text-muted">weekly net</span><span className={`num ${res.at_scale.weekly_net_usd < 0 ? "text-pass" : "text-muted"}`}>{usd(res.at_scale.weekly_net_usd)}</span>
                <span className="text-muted">annual net</span><span className={`num ${res.at_scale.annual_net_usd < 0 ? "text-pass" : "text-muted"}`}>{usd(res.at_scale.annual_net_usd)}</span>
                <span className="text-muted">cleared @ T0</span><span className="num">{res.pct_cleared_at_t0}%</span>
              </div>
            </Card>
            <div className="rounded-xl border border-dashed border-line-2 bg-bg-2 p-4 text-sm text-muted">
              <h4 className="mb-2 text-[13px] text-accent">Reading</h4>
              Sub-millisecond added latency on the common path and {res.pct_cleared_at_t0}% cleared at the free tier means the safe majority is never slowed. {res.judge_note}.
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function Replay() {
  const [rows, setRows] = useState<Scenario[] | null>(null), [loading, setLoading] = useState(false);
  const go = async () => { setLoading(true); try { const d = await api.replay(); setRows(d.scenarios); toast("Replay complete", `${d.scenarios.length} scenarios`, "ok"); } catch (e) { toast("Failed", String(e), "err"); } setLoading(false); };
  return (
    <Card desc="Oversight-off carries the full risk at zero savings; each ControlPlane policy trades escalations for lower residual risk — and every one is net-negative.">
      <button className="btn-primary" onClick={go} disabled={loading}>{loading ? "running…" : "Run replay"}</button>
      {rows && (
        <table className="mt-4 w-full border-collapse text-sm">
          <thead><tr className="text-left text-[10.5px] uppercase tracking-wide text-muted">
            <th className="border-b border-line p-2.5">scenario</th><th className="border-b border-line p-2.5 text-right">residual risk</th>
            <th className="border-b border-line p-2.5 text-right">risk ↓</th><th className="border-b border-line p-2.5 text-right">net $</th><th className="border-b border-line p-2.5 text-right">escalations</th></tr></thead>
          <tbody>{rows.map((s) => (
            <tr key={s.name}><td className="border-b border-line p-2.5">{s.name}{s.self_funding && <span className="badge badge-pass ml-2">self-funding</span>}</td>
              <td className="num border-b border-line p-2.5 text-right">{s.residual_risk.toFixed(4)}</td>
              <td className="num border-b border-line p-2.5 text-right">{s.risk_reduction_pct.toFixed(0)}%</td>
              <td className={`num border-b border-line p-2.5 text-right ${s.net_usd < 0 ? "text-pass" : "text-muted"}`}>{usd(s.net_usd)}</td>
              <td className="num border-b border-line p-2.5 text-right">{(s.escalation_rate * 100).toFixed(0)}%</td></tr>))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function Agents() {
  const [r, setR] = useState<AgentReceipt | null>(null), [loading, setLoading] = useState(false);
  const AC: Record<string, [string, string]> = { continue: ["#3fb950", "CONTINUE"], escalate: ["#d9a221", "FLAG"], abort: ["#f85149", "ABORT"] };
  const go = async () => { setLoading(true); try { setR(await api.agentDemo()); toast("Agent trajectory audited", "", "ok"); } catch (e) { toast("Failed", String(e), "err"); } setLoading(false); };
  return (
    <Card desc="A support agent hallucinates a “365-day premium refund” no source supports, then loops to confirm its own invention. The auditor watches risk compound step-by-step and aborts before the wrong answer reaches the user — saving the wasted steps.">
      <button className="btn-primary" onClick={go} disabled={loading}>{loading ? "running…" : "Run agent trajectory"}</button>
      {r && (
        <div className="mt-4">
          <div className="mb-2 text-xs text-faint">TASK · {r.task}</div>
          <div className="flex flex-col gap-1.5">
            {r.verdicts.map((v) => { const [c, l] = AC[v.action] || ["#888", v.action];
              return (
                <div key={v.index} className="grid grid-cols-[92px_1fr_auto] items-center gap-3 rounded-lg border border-line bg-panel-2 p-2.5" style={{ borderLeft: `3px solid ${c}` }}>
                  <span className="badge" style={{ background: `${c}22`, color: c }}>{l}</span>
                  <div className="text-sm"><b>step {v.index}</b> · risk <span className="num">{v.step_risk.toFixed(2)}</span> · cumulative <span className="num">{v.cumulative_risk.toFixed(2)}</span>{v.loop_repeat >= 2 && ` · loop x${v.loop_repeat}`}
                    <div className="font-mono text-[11px] text-faint">{v.reason}</div></div>
                  <div className="font-mono text-[11px] text-faint">{v.receipt_id}</div>
                </div>
              ); })}
          </div>
          <div className="mt-3.5 rounded-xl border border-dashed border-line-2 bg-bg-2 p-4 text-sm text-muted">
            <h4 className="mb-1 text-[13px]" style={{ color: r.aborted_at != null ? "#d9a221" : "#3fb950" }}>{r.final_action.toUpperCase()}</h4>
            {r.summary}. Executed {r.n_steps_executed}/{r.n_steps_planned} steps · {r.wasted_usd > 0 ? `saved ${usd(r.wasted_usd)} in avoided agent spend` : ""} · the wrong answer never reached the user.
          </div>
        </div>
      )}
    </Card>
  );
}

function Compliance() {
  const [p, setP] = useState<{ decisions: number; controls: ControlRow[] } | null>(null);
  const go = async () => { try { setP(await api.compliance()); toast("Compliance pack generated", "", "ok"); } catch (e) { toast("Failed", String(e), "err"); } };
  return (
    <Card desc="Governance stays policy-as-config; auditor-ready evidence is generated on demand from the tamper-evident receipts. An evidence aid, not a legal certification.">
      <div className="flex gap-2">
        <button className="btn-primary" onClick={go}>Generate evidence pack</button>
        <a className="btn" href={`${api.streamUrl().replace("/v1/oversight/stream", "/v1/oversight/compliance.md")}`} target="_blank" rel="noreferrer">⬇ download Markdown</a>
      </div>
      {p && (
        <table className="mt-4 w-full border-collapse text-sm">
          <thead><tr className="text-left text-[10.5px] uppercase tracking-wide text-muted">
            <th className="border-b border-line p-2.5">framework</th><th className="border-b border-line p-2.5">control</th><th className="border-b border-line p-2.5">evidence</th><th className="border-b border-line p-2.5">status</th></tr></thead>
          <tbody>{p.controls.map((c, i) => (
            <tr key={i}><td className="border-b border-line p-2.5">{c.framework}</td><td className="border-b border-line p-2.5">{c.control}</td>
              <td className="border-b border-line p-2.5 text-xs text-muted">{c.evidence}</td>
              <td className="border-b border-line p-2.5"><span className={`badge ${c.status === "evidenced" ? "badge-pass" : "badge-escalate"}`}>{c.status}</span></td></tr>))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function Detectors({ summary }: { summary: Summary | null }) {
  const m = summary?.models;
  const rows = [
    ["T0", "performance", "overconfidence, lexical groundedness, self-consistency", "SEP / semantic entropy"],
    ["T1", "performance", "HHEM-2.1 groundedness (model)", "MiniCheck / Lynx"],
    ["T2", "performance", "LLM-as-judge (VoI-gated)", "hosted or local (Ollama/Groq)"],
    ["T0", "responsibility", "regex/Luhn PII, prompt-injection, unsafe-content", "Presidio · PromptGuard-2 · Llama Guard 4"],
    ["T0", "cost", "model-overkill (route-down), semantic cache", "learned router · embedding cache"],
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2">
        <Kpi label="Groundedness" value={m?.groundedness ?? "—"} tone={m?.groundedness?.includes("hhem") ? "good" : undefined} foot="performance axis" />
        <Kpi label="PII" value={m?.pii ?? "—"} tone={m?.pii?.includes("presidio") ? "good" : undefined} foot="responsibility axis" />
        <Kpi label="Safety" value={m?.safety ?? "heuristic"} tone={m?.safety && m.safety !== "heuristic" ? "good" : undefined} foot="responsibility axis" />
        <Kpi label="Judge (T2)" value={m?.judge ?? "disabled"} tone={m?.judge && m.judge !== "disabled" ? "good" : undefined} foot="uncertain tail only" />
      </div>
      <Card title="Tiered cascade">
        <table className="w-full border-collapse text-sm">
          <thead><tr className="text-left text-[10.5px] uppercase tracking-wide text-muted">{["tier", "axis", "detector", "upgrade path"].map((h) => <th key={h} className="border-b border-line p-2.5">{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="border-b border-line p-2.5">{j === 2 && c.includes("(model)") ? <>{c.replace(" (model)", "")} <span className="rounded-md border border-line bg-panel px-1.5 py-0.5 text-[11px] text-muted">model</span></> : c}</td>)}</tr>)}</tbody>
        </table>
        <p className="mt-3 text-[12.5px] text-muted">On real HaluEval data the cheap lexical check scores F1 0.30; the VoI cascade climbing to HHEM on the uncertain tail reaches F1 0.76 (docs/EVIDENCE.md). Enable models with the <span className="rounded-md border border-line bg-panel px-1.5 py-0.5 text-[11px]">[ml]</span> extra or a judge backend (Groq/Ollama).</p>
      </Card>
    </div>
  );
}

function Help() {
  return (
    <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
      <Card title="The one-line integration">
        <p className="mb-2 text-[12.5px] text-muted">Point any OpenAI client at The Tower — nothing else changes:</p>
        <pre className="code">{`client = OpenAI(
  base_url="http://localhost:8000/v1",
  api_key="anything",
)`}</pre>
        <p className="mt-2.5 text-[12.5px] text-muted">Every response is then overseen inline: passed, annotated, auto-repaired from source, escalated to a human, or blocked — each with a signed receipt.</p>
      </Card>
      <Card title="The three coupled risks">
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <span style={{ color: AXIS_COLOR.performance }}>performance</span><span>wrong, or confidently wrong</span>
          <span style={{ color: AXIS_COLOR.cost }}>cost</span><span>a cheaper path to the same quality (this funds the rest)</span>
          <span style={{ color: AXIS_COLOR.responsibility }}>responsibility</span><span>unsafe, biased, or leaking data</span>
        </div>
        <p className="mt-2.5 text-[12.5px] text-muted">One verdict across all three — not three separate tools.</p>
      </Card>
      <Card title="Glossary">
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <span className="text-muted">VoI</span><span>value of information — run a check only if it could change the decision</span>
          <span className="text-muted">Net P&L</span><span>safety spend − cost saved; negative = self-funding</span>
          <span className="text-muted">Cleared @ T0</span><span>resolved by free checks (the fast path)</span>
          <span className="text-muted">Escalate</span><span>held for a human — the uncertain, high-stakes tail</span>
          <span className="text-muted">Receipt</span><span>the hash-chained audit record of one decision</span>
        </div>
      </Card>
      <Card title="A 60-second tour">
        <ol className="list-decimal pl-5 text-[13px] leading-8 text-muted">
          <li>Click <b className="text-ink">Send demo traffic</b> (top right).</li>
          <li><b className="text-ink">Overview</b>: watch the P&L go negative.</li>
          <li><b className="text-ink">Live feed</b>: click a row → see the VoI trace.</li>
          <li><b className="text-ink">Latency & scale</b>: run the benchmark.</li>
          <li><b className="text-ink">Agent oversight</b>: watch a looping agent get stopped.</li>
          <li><b className="text-ink">Compliance</b>: generate the evidence pack.</li>
        </ol>
      </Card>
    </div>
  );
}

/* ---- receipt drawer ---- */
function ReceiptDrawer({ receipt: r, onClose }: { receipt: Receipt; onClose: () => void }) {
  const trace = r.trace.filter((s) => s.tier > 0).map((s) =>
    `${s.ran ? "RAN " : "SKIP"} T${s.tier} ${s.detector.padEnd(20)} voi=${(s.voi || 0).toFixed(5)} vs cost=${(s.check_cost || 0).toFixed(5)}  (${s.reason})`).join("\n")
    || "all resolved at T0 — no higher-tier check was worth its cost";
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />
      <aside className="fixed right-0 top-0 z-50 h-full w-[min(600px,96vw)] overflow-auto border-l border-line bg-panel p-6">
        <button className="btn absolute right-4 top-4" onClick={onClose}><X size={14} /></button>
        <h3 className="text-[15px] font-semibold">{r.request_id} <Badge action={r.action} /></h3>
        <div className="mb-3 text-faint">{r.use_case} · {r.policy_id}</div>
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <span className="text-muted">stopping reason</span><span>{r.stopping_reason}</span>
          <span className="text-muted">expected loss</span><span className="num">{r.expected_loss_before.toFixed(4)} → {r.expected_loss_after.toFixed(4)}</span>
          <span className="text-muted">P&L</span><span className="num">saved {usd(r.pnl.cost_saved_usd)} · spend {usd(r.pnl.safety_spend_usd)} · <b className={r.pnl.net_usd < 0 ? "text-pass" : "text-muted"}>net {usd(r.pnl.net_usd)}</b></span>
        </div>
        <h4 className="mb-1.5 mt-4 text-[13px]">Per-axis verdict</h4>
        {Object.entries(r.per_axis).map(([a, o]) => o && (
          <div key={a} className="my-1.5"><div className="flex justify-between"><span>{a}</span><b className="num">{o.p_fail.toFixed(3)}</b></div>
            <div className="mt-1 h-1.5 overflow-hidden rounded bg-[#0e1620]"><div className="h-full" style={{ width: `${o.p_fail * 100}%`, background: AXIS_COLOR[a as keyof typeof AXIS_COLOR] }} /></div></div>
        ))}
        <h4 className="mb-1.5 mt-4 text-[13px]">Value-of-information trace</h4>
        <pre className="code whitespace-pre-wrap">{trace}</pre>
        {r.repaired_output && <><h4 className="mb-1.5 mt-4 text-[13px]">Delivered to user</h4><pre className="code whitespace-pre-wrap">{r.repaired_output}</pre></>}
        <h4 className="mb-1.5 mt-4 text-[13px]">Tamper-evident chain</h4>
        <div className="break-all font-mono text-[10.5px] text-faint">self {r.hash_self}<br />prev {r.hash_prev || "genesis"}</div>
      </aside>
    </>
  );
}
