"use client";
import { useEffect, useState } from "react";
import { ArrowRight, Gauge, ShieldCheck, Zap } from "lucide-react";
import { api, BenchmarkEval, Summary } from "@/lib/api";
import { usd } from "@/lib/format";
import { BrandMark } from "./ui";
import { ThemeToggle } from "./theme";
import { Architecture } from "./architecture";

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark size={28} />
      <div className="leading-tight"><b className="text-[15px]">ControlPlane</b><span className="block text-[11px] text-faint max-[360px]:hidden">The Tower</span></div>
    </div>
  );
}

// Proof numbers are derived live from the committed benchmark artifact (artifacts/aggregate_eval.json), never
// hardcoded, so the landing page can never drift out of sync with the Public benchmarks page. These strings are
// only the fallback shown before the artifact loads (or if the backend is cold).
const PROOF_FALLBACK = [
  { k: "Groundedness F1", v: "loading", s: "HaluEval, Fixed HHEM vs ControlPlane" },
  { k: "False-alarm rate", v: "loading", s: "same recall, fewer false positives" },
  { k: "Expensive checks avoided", v: "loading", s: "vs fixed verification" },
  { k: "Cleared at T0", v: "loading", s: "safe majority stays on the free tier" },
];

export function Landing({ onLaunch }: { onLaunch: (view?: string) => void }) {
  const [s, setS] = useState<Summary | null>(null);
  const [b, setB] = useState<BenchmarkEval | null>(null);
  useEffect(() => {
    api.summary().then(setS).catch(() => {});
    api.benchmark().then(setB).catch(() => {});
  }, []);

  // Scroll-triggered reveals: fade/slide each section in as it enters the viewport (transform+opacity only,
  // so it stays on the compositor). Falls back to showing everything if IntersectionObserver or motion is off.
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>(".reveal"));
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) return;  // CSS leaves everything visible
    const root = document.documentElement;
    root.classList.add("js-reveal");  // only now is it safe to hide, because we can un-hide
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    els.forEach((e) => io.observe(e));
    return () => { io.disconnect(); root.classList.remove("js-reveal"); };
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
      <nav className="glass sticky top-0 z-20 flex items-center gap-3 border-b border-line px-4 py-3 sm:gap-4 sm:px-6">
        <Logo />
        <span className="flex-1" />
        <a href="#architecture" className="hidden text-sm text-muted transition hover:text-ink sm:block">How it works</a>
        <a href="#proof" className="hidden text-sm text-muted transition hover:text-ink sm:block">Proof</a>
        <a href="https://github.com/dhruv-decoder/Hallucinators" target="_blank" rel="noreferrer" className="hidden text-sm text-muted transition hover:text-ink sm:block">GitHub</a>
        <ThemeToggle />
        <button className="btn-primary inline-flex items-center gap-1.5 whitespace-nowrap" onClick={() => onLaunch()}>Launch<span className="max-sm:hidden">&nbsp;dashboard</span> <ArrowRight size={15} /></button>
      </nav>

      {/* hero */}
      <header className="mx-auto max-w-[1080px] px-4 pb-10 pt-16 text-center sm:px-6 sm:pt-20">
        <div className="animate-fadeup mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-muted">
          <span className="h-1.5 w-1.5 animate-pulseglow rounded-full" style={{ background: "var(--accent)" }} /> Real-time oversight for enterprise AI
        </div>
        <h1 className="animate-fadeup font-bold leading-[1.05] tracking-tight" style={{ animationDelay: ".05s", fontSize: "clamp(2.1rem, 6.4vw, 3.75rem)" }}>
          Oversight that<br /><span style={{ color: "var(--accent)" }}>pays for itself.</span>
        </h1>
        <p className="animate-fadeup mx-auto mt-5 max-w-[620px] text-muted" style={{ animationDelay: ".1s", fontSize: "clamp(1rem, 2.4vw, 1.125rem)" }}>
          A layer in front of any model that decides, per response, <b className="text-ink">how much verification it&rsquo;s worth</b>,
          buying the cheapest signal first and letting cost savings fund the safety checks. One verdict across performance, cost, and responsibility.
        </p>
        <div className="animate-fadeup mt-8 flex flex-wrap items-center justify-center gap-3" style={{ animationDelay: ".15s" }}>
          <button className="btn-primary inline-flex items-center gap-1.5 px-5 py-2.5 text-[15px]" onClick={() => onLaunch()}>Launch the live Control Tower <ArrowRight size={16} /></button>
          <a href="#architecture" className="btn px-5 py-2.5 text-[15px]">See how it works</a>
        </div>
        {/* live ticker */}
        <div className="animate-fadeup mx-auto mt-12 grid max-w-[760px] grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line max-[440px]:grid-cols-1" style={{ animationDelay: ".2s" }}>
          {[
            ["Net benefit", net == null ? "live" : usd(-net), net == null ? "connecting" : net <= 0 ? "self-funding" : "this window"],
            ["Groundedness F1", f1 ?? "live", f1delta != null ? `HaluEval, +${f1delta.toFixed(3)} vs fixed` : "HaluEval, measured"],
            ["Expensive checks avoided", avoided != null ? `${avoided.toFixed(1)}%` : "live", "vs fixed HHEM, same recall"],
          ].map(([k, v, sub]) => (
            <div key={k} className="bg-panel px-5 py-4">
              <div className="text-[11px] uppercase tracking-wide text-faint">{k}</div>
              <div className="num mt-1 text-2xl font-bold" style={{ color: k === "Net benefit" && net != null && net <= 0 ? "var(--pass)" : "var(--ink)" }}>{v}</div>
              <div className="text-[11px] text-muted">{sub}</div>
            </div>
          ))}
        </div>
      </header>

      {/* proof */}
      <section id="proof" className="reveal border-y border-line bg-panel-2/40">
        <div className="mx-auto max-w-[1080px] px-4 py-16 sm:px-6">
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

      <Architecture onLaunch={onLaunch} />

      {/* one-line swap */}

      {/* CTA */}
      {/* one-line swap */}
      <section className="reveal mx-auto max-w-[1080px] px-4 sm:px-6 py-6">
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

      <section className="reveal mx-auto max-w-[1080px] px-4 sm:px-6 pb-24">
        <div className="card flex flex-col items-center gap-4 py-14 text-center" style={{ background: "radial-gradient(600px 200px at 50% 0%, var(--accent-dim), var(--grad-1))" }}>
          <ShieldCheck size={30} style={{ color: "var(--accent)" }} />
          <h2 className="text-3xl font-semibold tracking-tight">See it run live</h2>
          <p className="max-w-[520px] text-muted">Send demo traffic, watch the net benefit climb, benchmark the latency, and stop a looping agent, all in the browser.</p>
          <button className="btn-primary inline-flex items-center gap-1.5 px-5 py-2.5 text-[15px]" onClick={() => onLaunch()}>Launch the Control Tower <ArrowRight size={16} /></button>
        </div>
      </section>

      <footer className="border-t border-line px-6 py-8 text-center text-sm text-faint">
        ControlPlane · The Tower, Team Hallucinators · Accenture Innovation Challenge 2026
      </footer>
    </div>
  );
}
