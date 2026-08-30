import type { Action, Axis, Receipt } from "./api";

export const ACTION_COLOR: Record<Action, string> = {
  pass: "#3fb950", annotate: "#58a6ff", auto_repair: "#bc8cff", escalate: "#d9a221", block: "#f85149",
};
export const AXIS_COLOR: Record<Axis, string> = { performance: "#58a6ff", cost: "#3fb950", responsibility: "#f85149" };

// Adaptive precision: the demo's per-run P&L is a few cents, so show enough significant digits to see it move
// ($0.013, not a flat $0.01). Dollar-scale figures (projections) stay at 2 decimals.
export const usd = (n: number) => {
  const a = Math.abs(n);
  const dp = a === 0 ? 2 : a < 0.001 ? 5 : a < 1 ? 3 : 2;
  return (n < 0 ? "-$" : "$") + a.toFixed(dp);
};

export const fmtEta = (s: number | null) =>
  s == null ? "-" : s < 1 ? "<1s" : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;

export function worstAxis(r: Receipt): [Axis | null, number] {
  let a: Axis | null = null, p = -1;
  for (const [k, o] of Object.entries(r.per_axis)) if (o && o.p_fail > p) { p = o.p_fail; a = k as Axis; }
  return [a, Math.max(p, 0)];
}
