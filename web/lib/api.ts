// Typed client for the ControlPlane oversight API (FastAPI backend).
// In dev, calls go to /api/* which next.config rewrites to the backend (no CORS hop). In prod, set
// NEXT_PUBLIC_API_BASE to the deployed backend origin (CORS is enabled server-side).

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export type Axis = "performance" | "cost" | "responsibility";
export type Action = "pass" | "annotate" | "auto_repair" | "escalate" | "block";

export interface AxisOutcome { p_fail: number }
export interface Signal { name: string; axis: Axis; tier: number; score: number; p_fail?: number; latency_ms?: number }
export interface VoIStep { axis: Axis; detector: string; tier: number; voi: number; check_cost: number; ran: boolean; reason: string }
export interface Pnl { cost_saved_usd: number; safety_spend_usd: number; net_usd: number }
export interface Receipt {
  request_id: string; use_case: string; action: Action; policy_id: string; stopping_reason: string;
  per_axis: Partial<Record<Axis, AxisOutcome>>; signals: Signal[]; trace: VoIStep[];
  cost_opportunities: { name: string; recommendation: string; estimated_savings_usd: number }[];
  expected_loss_before: number; expected_loss_after: number; repaired_output?: string | null;
  pnl: Pnl; hash_self: string; hash_prev: string;
}
export interface Summary {
  requests: number; cost_saved_usd: number; safety_spend_usd: number; net_usd: number; self_funding: boolean;
  by_action: Partial<Record<Action, number>>; cleared_at_t0_pct: number; scrutiny: number; chain_valid: boolean;
  active_policy: string; policies: Record<string, string>; models: { groundedness: string; pii: string; safety?: string; judge: string };
}
export interface JobSnapshot {
  id: string; kind: string; status: "running" | "done" | "error"; progress: number; done: number; total: number;
  eta_seconds: number | null; elapsed_seconds: number; message: string; result: any; error: string | null;
}
export interface Scenario {
  name: string; residual_risk: number; risk_reduction_pct: number; net_usd: number; escalation_rate: number; self_funding: boolean;
}
export interface StepVerdict {
  index: number; step_risk: number; cumulative_risk: number; loop_repeat: number; action: string; reason: string; receipt_id: string;
}
export interface AgentReceipt {
  task: string; n_steps_planned: number; n_steps_executed: number; aborted_at: number | null; final_action: string;
  wasted_usd: number; summary: string; verdicts: StepVerdict[];
}
export interface ControlRow { framework: string; control: string; evidence: string; status: string }
export interface UseCaseSpec {
  use_case: string; weekly_volume: number; latency_budget: string; risk_tolerance: string;
  data_sensitivity: string; geo: string;
}
export interface GeneratedPolicy {
  profile_id: string; applied: boolean;
  knobs: { lambda_latency: number; cost_fail: Record<string, number>; block_threshold: number; escalate_threshold: number; annotate_threshold: number };
  projection: { weekly_volume: number; cleared_at_t0_pct: number; added_latency_p95_ms: number; escalation_rate: number; human_reviews_per_month: number; projected_monthly_net_usd: number; self_funding: boolean; note: string };
  rationale: string[]; recommended_detectors: string[]; compliance: string[];
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
async function jpost<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { method: "POST" });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  health: () => jget<{ ok: boolean; upstream: string; models: Summary["models"] }>("/healthz"),
  summary: () => jget<Summary>("/v1/oversight/summary"),
  receipts: (limit = 80) => jget<{ receipts: Receipt[] }>(`/v1/oversight/receipts?limit=${limit}`),
  simulate: () => jpost<{ processed: number }>("/v1/oversight/simulate"),
  setPolicy: (policy: string) =>
    fetch(`${API_BASE}/v1/oversight/policy`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ policy }),
    }).then((r) => r.json()),
  replay: () => jpost<{ scenarios: Scenario[] }>("/v1/oversight/replay"),
  agentDemo: () => jpost<AgentReceipt>("/v1/oversight/agent-demo"),
  compliance: () => jget<{ decisions: number; controls: ControlRow[] }>("/v1/oversight/compliance"),
  generatePolicy: (spec: UseCaseSpec, apply = false) =>
    fetch(`${API_BASE}/v1/oversight/policy/generate?apply=${apply ? 1 : 0}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec),
    }).then((r) => r.json() as Promise<GeneratedPolicy>),
  startBenchmark: (n: number, weekly: number) =>
    jpost<JobSnapshot>(`/v1/oversight/jobs/benchmark?n=${n}&weekly_volume=${weekly}`),
  job: (id: string) => jget<JobSnapshot>(`/v1/oversight/jobs/${id}`),
  streamUrl: () => `${API_BASE}/v1/oversight/stream`,
};
