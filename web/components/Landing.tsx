"use client";
import { useEffect, useState } from "react";
import {
  ArrowRight, CircleDollarSign, FileCheck2, GitBranch, Gauge, ShieldCheck, Workflow, Zap,
} from "lucide-react";
import { api, BenchmarkEval, Summary } from "@/lib/api";
import { usd } from "@/lib/format";
import { BrandMark } from "./ui";
import { ThemeToggle } from "./theme";

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark size={28} />
      <div className="leading-tight"><b className="text-[15px]">ControlPlane</b><span className="block text-[11px] text-faint">The Tower</span></div>
    </div>
  );
}

const AXES = [
  { c: "var(--annotate)", t: "Performance", d: "Is it wrong, or confidently wrong? Groundedness vs. source, self-consistency, and a model judge on the uncertain tail." },
  { c: "var(--pass)", t: "Cost", d: "Is there a cheaper path to the same quality? Route-downs and cache hits, the savings that fund the safety checks." },
  { c: "var(--block)", t: "Responsibility", d: "Is it unsafe or leaking data? PII, prompt-injection and unsafe-content gates, redacted or blocked before it ships." },
];
// Proof numbers are derived live from the committed benchmark artifact (artifacts/aggregate_eval.json), never
// hardcoded, so the landing page can never drift out of sync with the Public benchmarks page. These strings are
// only the fallback shown before the artifact loads (or if the backend is cold).
const PROOF_FALLBACK = [
  { k: "Groundedness F1", v: "loading", s: "HaluEval, Fixed HHEM vs ControlPlane" },
  { k: "False-alarm rate", v: "loading", s: "same recall, fewer false positives" },
  { k: "Expensive checks avoided", v: "loading", s: "vs fixed verification" },
  { k: "Cleared at T0", v: "loading", s: "safe majority stays on the free tier" },
];
const DIFF = [
  { icon: CircleDollarSign, t: "Self-funding P&L", d: "Cost-axis savings (real cache-bypass + route-down) offset the safety checks, a live ledger. A demonstrated mechanism; measured on the real-model path, counterfactual portions labelled as such." },
  { icon: Workflow, t: "Agentic oversight", d: "Extends to multi-step agents: catches compounding hallucinations and loops, aborting mid-run before the wrong answer ships." },
  { icon: FileCheck2, t: "Compliance pack", d: "Every decision maps to EU AI Act / ISO 42001 / NIST AI RMF controls, auditor-ready evidence, generated on demand." },
  { icon: GitBranch, t: "Tamper-evident receipts", d: "A hash-chained flight recorder: every verdict is auditable, with the value-of-information math behind it." },
];

export function Landing({ onLaunch }: { onLaunch: () => void }) {
  const [s, setS] = useState<Summary | null>(null);
  const [b, setB] = useState<BenchmarkEval | null>(null);
  useEffect(() => {
    api.summary().then(setS).catch(() => {});
    api.benchmark().then(setB).catch(() => {});
  }, []);
  const net = s?.net_usd ?? null;

  const cp = b?.strategies?.controlplane, fx = b?.strategies?.fixed_checks;
  const f1 = cp ? cp.confusion.performance.f1.toFixed(3) : null;
  const f1delta = cp && fx ? cp.confusion.performance.f1 - fx.confusion.performance.f1 : null;
  const fpr = cp ? cp.confusion.performance.fpr.toFixed(3) : null;
  const avoided = cp && fx && fx.expensive_checks_run ? (1 - cp.expensive_checks_run / fx.expensive_checks_run) * 100 : null;
  const t0 = cp ? cp.t0_clearance_pct : null;
  const PROOF = cp && fx ? [
    { k: "Groundedness F1", v: `${f1}`, s: `HaluEval${f1delta != null ? ` · +${f1delta.toFixed(3)} vs fixed HHEM` : ""}` },
    { k: "False-alarm rate", v: `${fpr}`, s: `down from ${fx.confusion.performance.fpr.toFixed(3)}, same recall ${cp.confusion.performance.recall.toFixed(3)}` },
    { k: "Expensive checks avoided", v: `${avoided?.toFixed(1)}%`, s: `${cp.expensive_checks_run} vs ${fx.expensive_checks_run} checks purchased` },
    { k: "Cleared at T0", v: `${t0}%`, s: "safe majority stays on the free tier" },
  ] : PROOF_FALLBACK;

  return (
    <div className="min-h-screen">
      {/* nav */}
      <nav className="glass sticky top-0 z-20 flex items-center gap-4 border-b border-line px-6 py-3">
        <Logo />
        <span className="flex-1" />
        <a href="#how" className="hidden text-sm text-muted transition hover:text-ink sm:block">How it works</a>
        <a href="#proof" className="hidden text-sm text-muted transition hover:text-ink sm:block">Proof</a>
        <a href="https://github.com/dhruv-decoder/Hallucinators" target="_blank" rel="noreferrer" className="hidden text-sm text-muted transition hover:text-ink sm:block">GitHub</a>
        <ThemeToggle />
        <button className="btn-primary inline-flex items-center gap-1.5" onClick={onLaunch}>Launch dashboard <ArrowRight size={15} /></button>
      </nav>

      {/* hero */}
      <header className="mx-auto max-w-[1080px] px-6 pb-10 pt-20 text-center">
        <div className="animate-fadeup mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-muted">
          <span className="h-1.5 w-1.5 animate-pulseglow rounded-full" style={{ background: "var(--accent)" }} /> Real-time oversight for enterprise AI
        </div>
        <h1 className="animate-fadeup text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl" style={{ animationDelay: ".05s" }}>
          Oversight that<br /><span style={{ color: "var(--accent)" }}>pays for itself.</span>
        </h1>
        <p className="animate-fadeup mx-auto mt-5 max-w-[620px] text-lg text-muted" style={{ animationDelay: ".1s" }}>
          A layer in front of any model that decides, per response, <b className="text-ink">how much verification it&rsquo;s worth</b>,
          buying the cheapest signal first and letting cost savings fund the safety checks. One verdict across performance, cost, and responsibility.
        </p>
        <div className="animate-fadeup mt-8 flex items-center justify-center gap-3" style={{ animationDelay: ".15s" }}>
          <button className="btn-primary inline-flex items-center gap-1.5 px-5 py-2.5 text-[15px]" onClick={onLaunch}>Launch the live Control Tower <ArrowRight size={16} /></button>
          <a href="#how" className="btn px-5 py-2.5 text-[15px]">See how it works</a>
        </div>
        {/* live ticker */}
        <div className="animate-fadeup mx-auto mt-12 grid max-w-[760px] grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line" style={{ animationDelay: ".2s" }}>
          {[
            ["Oversight P&L", net == null ? "live" : usd(net), net == null ? "connecting" : net < 0 ? "self-funding" : "this window"],
            ["Groundedness F1", f1 ?? "live", f1delta != null ? `HaluEval, +${f1delta.toFixed(3)} vs fixed` : "HaluEval, measured"],
            ["Expensive checks avoided", avoided != null ? `${avoided.toFixed(1)}%` : "live", "vs fixed HHEM, same recall"],
          ].map(([k, v, sub]) => (
            <div key={k} className="bg-panel px-5 py-4">
              <div className="text-[11px] uppercase tracking-wide text-faint">{k}</div>
              <div className="num mt-1 text-2xl font-bold" style={{ color: k === "Oversight P&L" && net != null && net < 0 ? "var(--pass)" : "var(--ink)" }}>{v}</div>
              <div className="text-[11px] text-muted">{sub}</div>
            </div>
          ))}
        </div>
      </header>

      {/* three axes */}
      <section className="mx-auto max-w-[1080px] px-6 py-16">
        <h2 className="text-center text-3xl font-semibold tracking-tight">One layer, three coupled risks, one verdict</h2>
        <p className="mx-auto mt-3 max-w-[560px] text-center text-muted">Not three separate tools shouting different things, a single economic decision across all three.</p>
        <div className="mt-10 grid grid-cols-3 gap-4 max-md:grid-cols-1">
          {AXES.map((a) => (
            <div key={a.t} className="card">
              <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg" style={{ background: `color-mix(in srgb, ${a.c} 15%, transparent)` }}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: a.c }} />
              </div>
              <h3 className="text-lg font-semibold">{a.t}</h3>
              <p className="mt-1.5 text-sm text-muted">{a.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* proof */}
      <section id="proof" className="border-y border-line bg-panel-2/40">
        <div className="mx-auto max-w-[1080px] px-6 py-16">
          <div className="mb-8 flex items-end justify-between gap-4 max-sm:flex-col max-sm:items-start">
            <div><h2 className="text-3xl font-semibold tracking-tight">Measured, not asserted</h2>
              <p className="mt-2 max-w-[540px] text-muted">Every number is reproducible from the repo, real public benchmarks and a real latency test, not slideware.</p></div>
            <span className="pill"><Gauge size={13} /> reproducible via <span className="num">make eval-real</span></span>
          </div>
          <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2">
            {PROOF.map((p) => (
              <div key={p.k} className="card">
                <div className="text-[11px] uppercase tracking-wide text-faint">{p.k}</div>
                <div className="num mt-1.5 text-2xl font-bold" style={{ color: "var(--accent)" }}>{p.v}</div>
                <div className="mt-1 text-xs text-muted">{p.s}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="mx-auto max-w-[1080px] px-6 py-16">
        <h2 className="text-center text-3xl font-semibold tracking-tight">The value-of-information cascade</h2>
        <p className="mx-auto mt-3 max-w-[600px] text-center text-muted">Only pay for a check when it could change the decision. Most responses clear instantly; the costly checks and humans are reserved for the uncertain, high-stakes tail.</p>
        <div className="mt-10 grid grid-cols-4 gap-3 max-lg:grid-cols-2">
          {[
            { n: "T0", t: "Free heuristics", d: "Overconfidence, lexical groundedness, PII/injection, microseconds, on every response." },
            { n: "T1", t: "Cheap models", d: "HHEM-2.1 groundedness, self-consistency, run only if the value beats the cost." },
            { n: "T2", t: "LLM judge", d: "A strong model verifies the ~1–3% still uncertain. Bought, not blanket-applied." },
            { n: "Act", t: "Pass · repair · escalate · block", d: "Auto-repair from source, redact/block leaks, or route to a human, with a receipt." },
          ].map((step, i) => (
            <div key={step.n} className="card relative">
              <div className="num mb-2 inline-flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--accent)" }}>{step.n}
                {i < 3 && <ArrowRight size={13} className="text-faint" />}</div>
              <h3 className="font-semibold">{step.t}</h3>
              <p className="mt-1 text-[13px] text-muted">{step.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* one-line swap */}
      <section className="mx-auto max-w-[1080px] px-6 py-6">
        <div className="card grid grid-cols-[1.1fr_1fr] gap-6 p-7 max-md:grid-cols-1">
          <div>
            <span className="pill mb-3"><Zap size={13} /> drop-in</span>
            <h2 className="text-2xl font-semibold tracking-tight">Swap one line. Nothing else changes.</h2>
            <p className="mt-2 text-muted">Point any OpenAI-compatible client at The Tower. Streaming, tools, and your app code all keep working, now every response is overseen inline.</p>
          </div>
          <pre className="code text-[13px] leading-relaxed">{`from openai import OpenAI

client = OpenAI(
  base_url="https://your-tower/v1",
  api_key="anything",
)
# every response now passes through
# the value-of-information cascade`}</pre>
        </div>
      </section>

      {/* differentiators */}
      <section className="mx-auto max-w-[1080px] px-6 py-16">
        <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
          {DIFF.map((d) => { const Icon = d.icon; return (
            <div key={d.t} className="card flex gap-4">
              <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg" style={{ background: "var(--accent-dim)", color: "var(--accent)" }}><Icon size={18} /></div>
              <div><h3 className="font-semibold">{d.t}</h3><p className="mt-1 text-sm text-muted">{d.d}</p></div>
            </div>
          ); })}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-[1080px] px-6 pb-24">
        <div className="card flex flex-col items-center gap-4 py-14 text-center" style={{ background: "radial-gradient(600px 200px at 50% 0%, var(--accent-dim), var(--grad-1))" }}>
          <ShieldCheck size={30} style={{ color: "var(--accent)" }} />
          <h2 className="text-3xl font-semibold tracking-tight">See it run live</h2>
          <p className="max-w-[520px] text-muted">Send demo traffic, watch the P&L go negative, benchmark the latency, and stop a looping agent, all in the browser.</p>
          <button className="btn-primary inline-flex items-center gap-1.5 px-5 py-2.5 text-[15px]" onClick={onLaunch}>Launch the Control Tower <ArrowRight size={16} /></button>
        </div>
      </section>

      <footer className="border-t border-line px-6 py-8 text-center text-sm text-faint">
        ControlPlane · The Tower, Team Hallucinators · Accenture Innovation Challenge 2026
      </footer>
    </div>
  );
}
