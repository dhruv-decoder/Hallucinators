"use client";
import { ArrowDown, ArrowRight } from "lucide-react";
import type { Action } from "@/lib/api";
import { ACTION_COLOR } from "@/lib/format";
import { cn } from "./ui";
import { M } from "./math";

/* ---- system architecture --------------------------------------------------------------------
   A layered diagram rather than a feature grid. Five numbered planes down a gutter, each with the
   components that live in it, and a labelled edge between every pair carrying the signal that
   actually crosses it. The point of the layer form is that it answers "where does this run and what
   does it hand on" in one read, which a row of cards cannot.

   Colour is spent in exactly two places: the three risk axes and the five verdicts. Everything else
   is neutral, so the coloured things read as the classification they are. */

const AXIS = { perf: "#58a6ff", cost: "#3fb950", resp: "#f85149" } as const;

type Node = {
  id: string;
  detail: string;
  /** Dashboard panel this component corresponds to, if there is one. */
  view?: string;
  tone?: string;
};

/** One component inside a layer. Monospace identifier, prose description, arrow when it opens a panel. */
function Unit({ n, onOpen }: { n: Node; onOpen: (v?: string) => void }) {
  const clickable = Boolean(n.view);
  const Tag = clickable ? "button" : "div";
  return (
    <Tag
      {...(clickable ? { type: "button" as const, onClick: () => onOpen(n.view) } : {})}
      className={cn(
        "group relative h-full w-full rounded-lg border border-line bg-panel px-3 py-2.5 text-left transition",
        clickable && "cursor-pointer hover:border-accent hover:bg-panel-2",
      )}
      style={n.tone ? { boxShadow: `inset 2px 0 0 ${n.tone}` } : undefined}
    >
      <div className="flex items-baseline gap-1.5">
        <span className="num flex-1 text-[12.5px] font-semibold tracking-tight">{n.id}</span>
        {clickable && (
          <ArrowRight size={12} className="flex-none translate-y-0.5 text-faint transition group-hover:translate-x-0.5 group-hover:text-accent" />
        )}
      </div>
      <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{n.detail}</p>
    </Tag>
  );
}

/** A numbered plane: identifier and name in the gutter, components in the body. */
function Layer({ id, name, role, children, accent }: {
  id: string; name: string; role: string; children: React.ReactNode; accent?: boolean;
}) {
  return (
    <section
      className={cn("grid grid-cols-[132px_1fr] gap-5 rounded-xl border p-4 max-md:grid-cols-1 max-md:gap-3",
        accent ? "border-accent/40" : "border-line")}
      style={{ background: accent ? "color-mix(in srgb, var(--accent) 4%, var(--panel-2))" : "var(--panel-2)" }}
    >
      <div className="max-md:flex max-md:items-baseline max-md:gap-2.5">
        <div className="num text-[11px] font-bold tracking-widest" style={{ color: "var(--accent)" }}>{id}</div>
        <div className="mt-0.5 text-[13px] font-semibold leading-tight max-md:mt-0">{name}</div>
        <div className="mt-1.5 text-[11px] leading-relaxed text-faint max-md:mt-0">{role}</div>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/** The edge between two layers, carrying the signal that crosses it. */
function Edge({ signal, note }: { signal: string; note?: string }) {
  return (
    <div className="grid grid-cols-[132px_1fr] gap-5 max-md:grid-cols-1 max-md:gap-0" aria-hidden>
      <div />
      <div className="flex items-center gap-2.5 py-2 pl-5">
        <ArrowDown size={13} className="flex-none text-faint" />
        <span className="num rounded border border-line bg-panel px-2 py-0.5 text-[11px] text-muted">{signal}</span>
        {note && <span className="text-[11px] text-faint">{note}</span>}
      </div>
    </div>
  );
}

export function Architecture({ onLaunch }: { onLaunch: (view?: string) => void }) {
  return (
    <section id="architecture" className="reveal mx-auto max-w-[1180px] px-4 py-16 sm:px-6">
      <div className="mx-auto max-w-[720px] text-center">
        <h2 className="text-3xl font-semibold tracking-tight">System architecture</h2>
        <p className="mt-3 text-muted">
          Five planes between your application and the model. Each one names what it hands to the next.
          Components marked with an arrow open the panel where you can watch them run.
        </p>
      </div>

      <div className="mt-10 flex flex-col">
        {/* ── client ── */}
        <div className="rounded-xl border border-dashed border-line-2 px-4 py-3">
          <div className="grid grid-cols-[132px_1fr] gap-5 max-md:grid-cols-1 max-md:gap-2">
            <div className="num text-[11px] font-bold tracking-widest text-faint">CLIENT</div>
            <p className="text-[12.5px] text-muted">
              Any OpenAI-compatible client. One line changes, <span className="num text-ink">base_url</span>,
              and streaming, tools and existing application code keep working.
            </p>
          </div>
        </div>

        <Edge signal="POST /v1/chat/completions" note="prompt, retrieved documents, use case" />

        {/* ── L1 ingress ── */}
        <Layer id="L1" name="Ingress" role="Runs before the model is called, and can end the request without calling it.">
          <div className="grid grid-cols-2 gap-2.5 max-sm:grid-cols-1">
            <Unit onOpen={onLaunch} n={{
              id: "injection_gate",
              detail: "Scans the prompt and every retrieved document. A poisoned knowledge-base article is the form of this attack that lands in production, because nothing the user typed looks wrong.",
              view: "hardcases", tone: AXIS.resp,
            }} />
            <Unit onOpen={onLaunch} n={{
              id: "response_cache",
              detail: "Exact and semantic lookup keyed on prompt, model, source and policy. A hit returns here and the upstream counter never moves.",
              view: "runtime", tone: AXIS.cost,
            }} />
          </div>
        </Layer>

        <Edge signal="cache miss" note="a hit short-circuits to L4 with no model call" />

        {/* ── L2 generation ── */}
        <Layer id="L2" name="Generation" role="The only layer that spends money on the model itself.">
          <div className="grid grid-cols-2 gap-2.5 max-sm:grid-cols-1">
            <Unit onOpen={onLaunch} n={{
              id: "upstream",
              detail: "The model under oversight. Provider-agnostic; the layer is unchanged by which one you point at.",
              view: "detectors",
            }} />
            <Unit onOpen={onLaunch} n={{
              id: "route_down",
              detail: "A simple prompt on a flagship is served by a smaller model instead. The avoided flagship price is booked as the counterfactual.",
              view: "pnl", tone: AXIS.cost,
            }} />
          </div>
        </Layer>

        <Edge signal="candidate response" note="not yet shown to anyone" />

        {/* ── L3 evaluation ── */}
        <Layer id="L3" accent name="Evaluation" role="The value-of-information cascade. Every paid check is a purchase decision.">
          <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-stretch gap-2 max-lg:grid-cols-1">
            <Unit onOpen={onLaunch} n={{
              id: "T0 · free",
              detail: "Lexical groundedness, overconfidence, identifiers, injection, unsafe content, bias. Microseconds, on every response.",
              view: "detectors",
            }} />
            <Gate />
            <Unit onOpen={onLaunch} n={{
              id: "T1 · small models",
              detail: "HHEM-2.1 entailment and self-consistency across samples. Tens of milliseconds.",
              view: "detectors",
            }} />
            <Gate />
            <Unit onOpen={onLaunch} n={{
              id: "T2 · model judge",
              detail: "gpt-oss-120b verifying the claims against the source. Roughly a second, so it is bought last and rarely.",
              view: "voi",
            }} />
          </div>

          <div className="mt-3 rounded-lg border border-line bg-panel px-4 py-3">
            <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="num text-[11px] font-bold tracking-widest" style={{ color: "var(--accent)" }}>STOPPING RULE</span>
              <span className="text-[11.5px] text-muted">buy the next check only when its information is worth more than its price</span>
            </div>
            <div className="scroll-x">
              <div className="min-w-max py-1">
                <M tex="\text{buy} \iff \underbrace{\eta \cdot \big[\min(p C,\, m) - p\min(m,\, C)\big]}_{\text{value of information}} \cdot s \;>\; \underbrace{c + \lambda \ell}_{\text{price of the check}}" />
              </div>
            </div>
            <p className="mt-2 text-[11.5px] leading-relaxed text-muted">
              <span className="num text-ink">p</span> calibrated failure probability ·
              <span className="num text-ink"> C</span> cost of a miss ·
              <span className="num text-ink"> m</span> cost of mitigating ·
              <span className="num text-ink"> η</span> how much the check resolves ·
              <span className="num text-ink"> s</span> adaptive scrutiny ·
              <span className="num text-ink"> c, λℓ</span> the check&rsquo;s dollars and priced latency.
              Every term but <span className="num text-ink">η</span> comes from the policy, which is why changing
              a business fact changes which checks get bought.
            </p>
          </div>

          <div className="mt-2.5 grid grid-cols-3 gap-2.5 max-lg:grid-cols-1">
            <Unit onOpen={onLaunch} n={{ id: "axis · performance", detail: "Wrong, or confidently wrong.", view: "quadrant", tone: AXIS.perf }} />
            <Unit onOpen={onLaunch} n={{ id: "axis · cost", detail: "A cheaper path to the same answer. Funds the other two.", view: "pnl", tone: AXIS.cost }} />
            <Unit onOpen={onLaunch} n={{ id: "axis · responsibility", detail: "Leaking, biased, or unsafe.", view: "review", tone: AXIS.resp }} />
          </div>
        </Layer>

        <Edge signal="p_fail per axis" note="one calibrated probability each, not three separate alerts" />

        {/* ── L4 decision ── */}
        <Layer id="L4" name="Decision" role="Turns probabilities into something that happens to the response.">
          <div className="grid grid-cols-5 gap-2 max-lg:grid-cols-2 max-sm:grid-cols-1">
            {(["pass", "annotate", "auto_repair", "escalate", "block"] as Action[]).map((a) => (
              <div key={a} className="rounded-lg border border-line bg-panel px-3 py-2.5"
                style={{ boxShadow: `inset 2px 0 0 ${ACTION_COLOR[a]}` }}>
                <div className="num text-[12.5px] font-semibold">{a.replace("_", "-")}</div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{VERDICT[a]}</p>
              </div>
            ))}
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-2.5 max-sm:grid-cols-1">
            <Unit onOpen={onLaunch} n={{
              id: "policy_profile",
              detail: "Thresholds and costs generated from latency budget, risk appetite, data sensitivity and geography. These are the same constants the stopping rule reads.",
              view: "configure",
            }} />
            <Unit onOpen={onLaunch} n={{
              id: "stream_guard",
              detail: "On a streamed response a token cannot be recalled, so digit runs are buffered until the surrounding text proves safe, and the stream is cut if it does not.",
              view: "streamguard", tone: AXIS.resp,
            }} />
          </div>
        </Layer>

        <Edge signal="verdict + delivered text" />

        {/* ── L5 record ── */}
        <Layer id="L5" name="Record" role="What makes the layer accountable after the fact, and better over time.">
          <div className="grid grid-cols-4 gap-2.5 max-lg:grid-cols-2 max-sm:grid-cols-1">
            <Unit onOpen={onLaunch} n={{
              id: "receipt_chain",
              detail: "Prompt, source, candidate, delivered text and every check considered. Redacted, then hashed with the previous receipt.",
              view: "feed",
            }} />
            <Unit onOpen={onLaunch} n={{
              id: "pnl_ledger",
              detail: "Savings booked against check spend, per request.",
              view: "pnl", tone: AXIS.cost,
            }} />
            <Unit onOpen={onLaunch} n={{
              id: "review_queue",
              detail: "The uncertain tail held for a person, as Article 14 requires.",
              view: "review",
            }} />
            <Unit onOpen={onLaunch} n={{
              id: "compliance_pack",
              detail: "Receipts mapped to EU AI Act, ISO 42001 and NIST AI RMF controls.",
              view: "compliance",
            }} />
          </div>
        </Layer>

        {/* ── feedback ── */}
        <div className="grid grid-cols-[132px_1fr] gap-5 max-md:grid-cols-1 max-md:gap-0">
          <div />
          <div className="flex items-center gap-2.5 py-3 pl-5">
            <ArrowRight size={13} className="flex-none -rotate-90 text-faint" aria-hidden />
            <span className="num rounded border px-2 py-0.5 text-[11px]"
              style={{ borderColor: "color-mix(in srgb, var(--accent) 40%, var(--line))", color: "var(--accent)" }}>
              feedback to L3
            </span>
            <span className="text-[11.5px] text-muted">
              A reviewer&rsquo;s verdict refits the calibrator for exactly the detectors that fired, so the
              probabilities the stopping rule reads improve from real use.
            </span>
          </div>
        </div>
      </div>

      {/* evidence sits beside the request path rather than inside it */}
      <div className="mt-10 rounded-xl border border-dashed border-line-2 p-4 sm:p-5">
        <div className="mb-3.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="num text-[11px] font-bold tracking-widest text-faint">EVIDENCE</span>
          <h3 className="text-[15px] font-semibold tracking-tight">How to check any of it</h3>
        </div>
        <div className="grid grid-cols-4 gap-2.5 max-lg:grid-cols-2 max-sm:grid-cols-1">
          {([
            ["playground", "Send a prompt and watch a real model be overseen, with every check shown.", "playground"],
            ["failure_analysis", "Which failure families still break a current model, over 65 live runs.", "hardcases"],
            ["benchmarks", "Fixed model checking against this cascade on 500 labelled HaluEval examples.", "benchmarks"],
            ["risk_certificate", "A conformal bound on how often real failures escape, with the derivation.", "guarantee"],
          ] as [string, string, string][]).map(([id, detail, view]) => (
            <Unit key={id} onOpen={onLaunch} n={{ id, detail, view }} />
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

/** The decision point between two tiers. Deliberately drawn as a gate, not an arrow. */
function Gate() {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-1 max-lg:flex-row max-lg:py-2">
      <span className="hidden w-px flex-1 lg:block" style={{ background: "var(--line-2)" }} />
      <span className="num whitespace-nowrap rounded border px-2 py-1 text-[10.5px] font-semibold"
        style={{ borderColor: "color-mix(in srgb, var(--accent) 45%, var(--line))", color: "var(--accent)" }}>
        VoI &gt; cost
      </span>
      <span className="hidden w-px flex-1 lg:block" style={{ background: "var(--line-2)" }} />
      <ArrowRight size={12} className="text-faint lg:hidden" />
    </div>
  );
}

const VERDICT: Record<Action, string> = {
  pass: "Forwarded unchanged.",
  annotate: "Forwarded with a caveat.",
  auto_repair: "Replaced with the grounded answer, only when the source is unambiguous.",
  escalate: "Held for a person.",
  block: "Not forwarded at all.",
};
