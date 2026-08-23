"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Crosshair, Cpu, Gauge, History, LayoutGrid, LifeBuoy, Rss, ScrollText, Wallet, Workflow, X,
} from "lucide-react";
import { AgentReceipt, api, ControlRow, Receipt, Scenario, Summary } from "@/lib/api";
import { ACTION_COLOR, AXIS_COLOR, fmtEta, usd, worstAxis } from "@/lib/format";
import { Badge, Card, Kpi, ProgressBar, toast, Toaster } from "./ui";
import { QuadrantChart, Sparkline } from "./charts";
import { ThemeToggle } from "./theme";

type View = "overview" | "feed" | "quadrant" | "pnl" | "benchmark" | "replay" | "agents" | "compliance" | "detectors" | "help";
const NAV: { group: string; items: { id: View; label: string; icon: any }[] }[] = [
  { group: "Monitor", items: [
    { id: "overview", label: "Overview", icon: LayoutGrid }, { id: "feed", label: "Live feed", icon: Rss },
    { id: "quadrant", label: "Confidently-wrong", icon: Crosshair }, { id: "pnl", label: "Oversight P&L", icon: Wallet } ] },
  { group: "Prove", items: [
    { id: "benchmark", label: "Latency & scale", icon: Gauge }, { id: "replay", label: "What-If replay", icon: History },
    { id: "agents", label: "Agent oversight", icon: Workflow } ] },
  { group: "Govern", items: [
    { id: "compliance", label: "Compliance", icon: ScrollText }, { id: "detectors", label: "Detectors & models", icon: Cpu },
    { id: "help", label: "Getting started", icon: LifeBuoy } ] },
];
const TITLES: Record<View, [string, string]> = {
  overview: ["Overview", "One verdict across performance, cost, and responsibility — in real time"],
  feed: ["Live feed", "Every decision, as it happens — the audit trail behind each response"],
  quadrant: ["Confidently-wrong map", "The danger zone we exist to catch: sure of itself and wrong"],
  pnl: ["Oversight P&L", "Safer AND cheaper — a negative price tag, measured not asserted"],
  benchmark: ["Latency & scale", "Does oversight slow the model down? Measure it."],
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
          <button className="btn-primary" disabled={busy} onClick={sendTraffic}>{busy ? "running…" : "▶ Send demo traffic"}</button>
        </header>

        <main className="mx-auto w-full max-w-[1480px] p-6">
          {view === "overview" && <Overview summary={summary} net={net} receipts={receipts} onOpen={setDrawer} />}
          {view === "feed" && <Feed receipts={receipts} onOpen={setDrawer} />}
          {view === "quadrant" && <Quadrant receipts={receipts} />}
          {view === "pnl" && <PnlView summary={summary} net={net} />}
          {view === "benchmark" && <Benchmark />}
          {view === "replay" && <Replay />}
          {view === "agents" && <Agents />}
          {view === "compliance" && <Compliance />}
          {view === "detectors" && <Detectors summary={summary} />}
          {view === "help" && <Help />}
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
function Overview({ summary, net, receipts, onOpen }: { summary: Summary | null; net: number[]; receipts: Receipt[]; onOpen: (r: Receipt) => void }) {
  const s = summary;
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
      <div className="grid grid-cols-3 gap-3">
        <Kpi label="Groundedness" value={m?.groundedness ?? "—"} tone={m?.groundedness?.includes("hhem") ? "good" : undefined} foot="performance axis" />
        <Kpi label="PII" value={m?.pii ?? "—"} tone={m?.pii?.includes("presidio") ? "good" : undefined} foot="responsibility axis" />
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
