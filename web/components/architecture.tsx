"use client";
import { ArrowRight } from "lucide-react";
import type { Action } from "@/lib/api";
import { ACTION_COLOR } from "@/lib/format";
import { cn } from "./ui";

/* ---- system architecture --------------------------------------------------------------------
   The one picture a visitor should be able to read before opening the product. It follows a single
   request all the way through, and every component names the panel that shows it working, so the
   diagram doubles as the table of contents for the dashboard. */

type Node = {
  id: string;
  title: string;
  detail: string;
  /** Dashboard panel this component corresponds to, if there is one. */
  view?: string;
  /** Colour role, used sparingly: only the three risk axes and the verdicts are coloured. */
  tone?: string;
};

function ArchNode({ n, onOpen, compact }: { n: Node; onOpen: (v?: string) => void; compact?: boolean }) {
  const clickable = Boolean(n.view);
  const Tag = clickable ? "button" : "div";
  return (
    <Tag
      {...(clickable ? { onClick: () => onOpen(n.view), type: "button" as const } : {})}
      className={cn(
        "group relative w-full rounded-xl border bg-panel p-3.5 text-left transition",
        clickable ? "cursor-pointer border-line hover:-translate-y-0.5 hover:border-accent" : "border-line",
        compact && "p-3",
      )}
      style={n.tone ? { borderLeftWidth: 3, borderLeftColor: n.tone } : undefined}
    >
      <div className="flex items-start gap-2">
        <h4 className={cn("flex-1 font-semibold tracking-tight", compact ? "text-[13px]" : "text-[14px]")}>
          {n.title}
        </h4>
        {clickable && (
          <ArrowRight size={13} className="mt-0.5 flex-none text-faint transition group-hover:translate-x-0.5 group-hover:text-accent" />
        )}
      </div>
      <p className="mt-1 text-[12px] leading-relaxed text-muted">{n.detail}</p>
    </Tag>
  );
}

/** A labelled band grouping the components that belong to one stage of the request. */
function ArchStage({ step, title, blurb, children, accent }: {
  step: string; title: string; blurb: string; children: React.ReactNode; accent?: boolean;
}) {
  return (
    <div className={cn("rounded-2xl border p-4 sm:p-5", accent ? "border-accent/40" : "border-line")}
      style={{ background: accent ? "color-mix(in srgb, var(--accent) 4%, var(--panel-2))" : "var(--panel-2)" }}>
      <div className="mb-3.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="num text-[11px] font-bold" style={{ color: "var(--accent)" }}>{step}</span>
        <h3 className="text-[15px] font-semibold tracking-tight">{title}</h3>
        <p className="w-full text-[12.5px] text-muted sm:w-auto sm:flex-1">{blurb}</p>
      </div>
      {children}
    </div>
  );
}

/** The connector between two stages, with the condition that governs the hand-off. */
function ArchFlow({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-2.5" aria-hidden>
      <span className="h-4 w-px" style={{ background: "var(--line-2)" }} />
      {label && <span className="rounded-full border border-line bg-panel px-2.5 py-0.5 text-[11px] text-muted">{label}</span>}
      <span className="h-4 w-px" style={{ background: "var(--line-2)" }} />
    </div>
  );
}

export function Architecture({ onLaunch }: { onLaunch: (view?: string) => void }) {
  const AXIS = { perf: "#58a6ff", cost: "#3fb950", resp: "#f85149" };
  return (
    <section id="architecture" className="reveal mx-auto max-w-[1180px] px-4 sm:px-6 py-16">
      <div className="mx-auto max-w-[760px] text-center">
        <h2 className="text-3xl font-semibold tracking-tight">How one response is handled</h2>
        <p className="mt-3 text-muted">
          ControlPlane sits between your application and the model. Follow a single request down the page:
          what happens before the model is called, how much verification the answer earns, what is done about
          it, and what is left behind. Every component opens the panel that shows it working.
        </p>
      </div>

      <div className="mt-10 flex flex-col">
        {/* 1 ─ the request arrives */}
        <ArchStage step="01" title="A request arrives"
          blurb="Point any OpenAI client at the gateway. Streaming, tools and your existing code keep working.">
          <div className="grid grid-cols-3 items-stretch gap-3 max-lg:grid-cols-1">
            <ArchNode onOpen={onLaunch} n={{
              id: "app", title: "Your application",
              detail: "One line changes: base_url. Nothing else in your code moves.",
              view: "api",
            }} />
            <ArchNode onOpen={onLaunch} n={{
              id: "gate", title: "Injection gate",
              detail: "Reads the prompt and every retrieved document. A poisoned knowledge-base article is the attack that actually lands, because nothing the user typed looks wrong.",
              view: "hardcases", tone: AXIS.resp,
            }} />
            <ArchNode onOpen={onLaunch} n={{
              id: "cache", title: "Response cache",
              detail: "A repeat request is served from store and the model is never called. Watch the upstream counter stay flat.",
              view: "runtime", tone: AXIS.cost,
            }} />
          </div>
        </ArchStage>

        <ArchFlow label="cache miss, so the model answers" />

        {/* 2 ─ the cascade */}
        <ArchStage step="02" accent title="The answer earns its verification"
          blurb="A check runs only when the information it buys is worth more than it costs in money and latency.">
          <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-stretch gap-2 max-lg:grid-cols-1">
            <ArchNode compact onOpen={onLaunch} n={{
              id: "t0", title: "T0 · free heuristics",
              detail: "Groundedness overlap, overconfidence, identifiers, injection, bias. Runs on everything, in milliseconds. Most traffic stops here.",
              view: "detectors",
            }} />
            <VoiGate />
            <ArchNode compact onOpen={onLaunch} n={{
              id: "t1", title: "T1 · cheap models",
              detail: "HHEM-2.1 entailment and self-consistency. Bought when the free tier left the answer uncertain.",
              view: "detectors",
            }} />
            <VoiGate />
            <ArchNode compact onOpen={onLaunch} n={{
              id: "t2", title: "T2 · model judge",
              detail: "A strong model verifies the small remainder. Bought last, and rarely.",
              view: "voi",
            }} />
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3 max-lg:grid-cols-1">
            {([
              ["Performance", AXIS.perf, "Is it wrong, or confidently wrong?", "quadrant"],
              ["Cost", AXIS.cost, "Was there a cheaper path to the same quality? This axis funds the others.", "pnl"],
              ["Responsibility", AXIS.resp, "Is it leaking, biased, or unsafe?", "review"],
            ] as [string, string, string, string][]).map(([t, c, d, v]) => (
              <ArchNode key={t} compact onOpen={onLaunch} n={{ id: t, title: t, detail: d, view: v, tone: c }} />
            ))}
          </div>
          <p className="mt-3 text-center text-[12px] text-muted">
            Three coupled risks, judged together into one verdict, rather than three tools reporting separately.
          </p>
        </ArchStage>

        <ArchFlow label="one calibrated probability per axis" />

        {/* 3 ─ act */}
        <ArchStage step="03" title="Something is done about it"
          blurb="The action is chosen from the probabilities and the policy for this use case.">
          <div className="grid grid-cols-5 gap-2 max-lg:grid-cols-2 max-sm:grid-cols-1">
            {(["pass", "annotate", "auto_repair", "escalate", "block"] as Action[]).map((a) => (
              <div key={a} className="rounded-xl border border-line bg-panel p-3"
                style={{ borderLeftWidth: 3, borderLeftColor: ACTION_COLOR[a] }}>
                <div className="text-[13px] font-semibold">{a.replace("_", "-")}</div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{ACTION_SHORT[a]}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 max-md:grid-cols-1">
            <ArchNode onOpen={onLaunch} n={{
              id: "sg", title: "StreamGuard",
              detail: "On a streaming response there is no taking tokens back, so digits are held in a buffer until the surrounding text proves safe, and the stream is cut if it does not.",
              view: "streamguard", tone: AXIS.resp,
            }} />
            <ArchNode onOpen={onLaunch} n={{
              id: "policy", title: "Policy profile",
              detail: "The thresholds and costs that decide the action, generated from your latency budget, risk appetite, data sensitivity and geography.",
              view: "configure",
            }} />
          </div>
        </ArchStage>

        <ArchFlow label="every decision, kept" />

        {/* 4 ─ what is left behind */}
        <ArchStage step="04" title="What is left behind"
          blurb="The parts that make the layer accountable after the fact, and better over time.">
          <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
            <ArchNode onOpen={onLaunch} n={{
              id: "receipt", title: "Hash-chained receipt",
              detail: "The prompt, the source, what the model said, what the user received, and every check considered. Altering one breaks the chain.",
              view: "feed",
            }} />
            <ArchNode onOpen={onLaunch} n={{
              id: "pnl", title: "Oversight P&L",
              detail: "Savings from route-downs and cache hits, booked against what the checks cost.",
              view: "pnl", tone: AXIS.cost,
            }} />
            <ArchNode onOpen={onLaunch} n={{
              id: "review", title: "Human review",
              detail: "The uncertain tail waits for a person, and each verdict recalibrates the detectors that fired.",
              view: "review",
            }} />
            <ArchNode onOpen={onLaunch} n={{
              id: "compliance", title: "Compliance pack",
              detail: "Receipts mapped to EU AI Act, ISO 42001 and NIST AI RMF controls, generated on demand.",
              view: "compliance",
            }} />
          </div>
        </ArchStage>
      </div>

      {/* the evidence surfaces, which sit alongside the request path rather than inside it */}
      <div className="mt-8 rounded-2xl border border-dashed border-line-2 p-4 sm:p-5">
        <div className="mb-3.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="num text-[11px] font-bold text-faint">EVIDENCE</span>
          <h3 className="text-[15px] font-semibold tracking-tight">How to check any of this</h3>
          <p className="w-full text-[12.5px] text-muted sm:w-auto sm:flex-1">
            Every claim above has a panel that shows the working.
          </p>
        </div>
        <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
          {([
            ["Playground", "Send your own prompt and watch a real model get overseen.", "playground"],
            ["Hard cases", "Which failure modes still break a modern model, measured over repeated live runs.", "hardcases"],
            ["Public benchmarks", "Fixed model checking against this cascade on the same labelled examples.", "benchmarks"],
            ["Risk guarantee", "A certificate bounding how often real failures escape, with the derivation.", "guarantee"],
          ] as [string, string, string][]).map(([t, d, v]) => (
            <ArchNode key={t} onOpen={onLaunch} n={{ id: t, title: t, detail: d, view: v }} />
          ))}
        </div>
      </div>

      <div className="mt-8 text-center">
        <button className="btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-[15px]" onClick={() => onLaunch()}>
          Open the Control Tower <ArrowRight size={16} />
        </button>
      </div>
    </section>
  );
}

/** The decision point between two tiers. This is the idea the whole product turns on. */
function VoiGate() {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-1 py-2 max-lg:flex-row max-lg:py-3">
      <span className="hidden h-full w-px lg:block" style={{ background: "var(--line-2)" }} />
      <span className="whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px]"
        style={{ borderColor: "color-mix(in srgb, var(--accent) 45%, var(--line))", color: "var(--accent)" }}>
        worth it?
      </span>
      <ArrowRight size={13} className="text-faint lg:rotate-90" />
    </div>
  );
}

const ACTION_SHORT: Record<Action, string> = {
  pass: "Forwarded unchanged.",
  annotate: "Forwarded with a caveat.",
  auto_repair: "Replaced with the grounded answer, when the source is unambiguous.",
  escalate: "Held for a person.",
  block: "Not forwarded at all.",
};
