import type { Action, Axis, Receipt } from "./api";

export const ACTION_COLOR: Record<Action, string> = {
  pass: "#3fb950", annotate: "#58a6ff", auto_repair: "#bc8cff", escalate: "#d9a221", block: "#f85149",
};
export const AXIS_COLOR: Record<Axis, string> = { performance: "#58a6ff", cost: "#3fb950", responsibility: "#f85149" };

export const usd = (n: number) =>
  (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(n !== 0 && Math.abs(n) < 0.01 ? 5 : 2);

export const fmtEta = (s: number | null) =>
  s == null ? "-" : s < 1 ? "<1s" : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;

export function worstAxis(r: Receipt): [Axis | null, number] {
  let a: Axis | null = null, p = -1;
  for (const [k, o] of Object.entries(r.per_axis)) if (o && o.p_fail > p) { p = o.p_fail; a = k as Axis; }
  return [a, Math.max(p, 0)];
}
