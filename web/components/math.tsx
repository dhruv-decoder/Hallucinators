"use client";
import katex from "katex";
import { useMemo } from "react";

// Typeset notation, not ASCII art. A risk certificate is the most technical claim the product makes, so
// the one place a reviewer looks hardest has to be the one place the typography is beyond question.

function render(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex, {
      displayMode: display,
      throwOnError: false,
      strict: false,
      trust: false,
      output: "html",
    });
  } catch {
    return tex; // never let a malformed expression blank the panel
  }
}

/** A display equation, optionally captioned. */
export function Eq({ tex, caption }: { tex: string; caption?: string }) {
  const html = useMemo(() => render(tex, true), [tex]);
  return (
    <div className="eq">
      {caption && <span className="eq-label t-label">{caption}</span>}
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}

/** Inline maths inside running prose. */
export function M({ tex }: { tex: string }) {
  const html = useMemo(() => render(tex, false), [tex]);
  return <span className="katex-inline" dangerouslySetInnerHTML={{ __html: html }} />;
}

/** A numbered step in a derivation: a rule, a heading, and its body. */
export function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="deriv">
      <h4 className="t-h2 mb-2 flex items-baseline gap-2">
        <span className="num text-[12px] font-semibold" style={{ color: "var(--accent)" }}>{n}</span>
        {title}
      </h4>
      <div className="t-body text-muted">{children}</div>
    </section>
  );
}
