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
  requests: number; measured_requests: number; cost_saved_usd: number; safety_spend_usd: number; net_usd: number;
  human_review_usd: number; self_funding: boolean;
  projection: { weekly_volume: number; weekly_net_usd: number; annual_net_usd: number; note: string };
  by_action: Partial<Record<Action, number>>; cleared_at_t0_pct: number; scrutiny: number; chain_valid: boolean;
  active_policy: string; policies: Record<string, string>; models: { groundedness: string; pii: string; safety?: string; judge: string };
}
export interface JobSnapshot {
  id: string; kind: string; status: "running" | "done" | "error"; progress: number; done: number; total: number;
  eta_seconds: number | null; elapsed_seconds: number; message: string; result: any; error: string | null;
}
export interface Scenario {
  name: string; residual_risk: number; risk_reduction_pct: number; net_usd: number;
  human_review_usd: number; total_cost_usd: number; escalation_rate: number; self_funding: boolean;
}
export interface StepVerdict {
  index: number; step_risk: number; cumulative_risk: number; loop_repeat: number; action: string; reason: string; receipt_id: string;
}
export interface AgentReceipt {
  task: string; n_steps_planned: number; n_steps_executed: number; aborted_at: number | null; final_action: string;
  wasted_usd: number; summary: string; verdicts: StepVerdict[];
}
export interface ControlRow { framework: string; control: string; evidence: string; status: string }
export interface PlaygroundResult {
  source: string; model: string; candidate: string; final: string; modified: boolean; cache_hit?: boolean; cache_hit_kind?: string; cache_similarity?: number | null;
  controlplane: { action: Action; per_axis_p_fail: Partial<Record<Axis, number>>; stopping_reason: string; net_usd: number; added_latency_ms: number };
  receipt: Receipt;
}
export interface UseCaseSpec {
  use_case: string; weekly_volume: number; latency_budget: string; risk_tolerance: string;
  data_sensitivity: string; geo: string;
}
export interface WarmupStatus {
  enabled: boolean; ready: boolean; status: "disabled" | "pending" | "warming" | "ready" | "error";
  elapsed_seconds: number | null; error: string | null;
  components: Record<string, { status: string; elapsed_seconds?: number; error?: string }>;
}
export interface CacheStatus {
  mode: string; enabled: boolean; threshold: number; entries: number; max_entries: number;
  ttl_seconds: number; embedding_model: string | null; upstream_calls: number; cache_hits: number;
  exact_cache_hits: number; semantic_cache_hits: number; cache_misses: number;
}
export interface InformativenessStatus {
  artifact: string; loaded: boolean;
  detectors: Record<string, { runtime_eta: number; source: string }>;
}
export interface RuntimeObservability {
  uptime_seconds: number; requests: number; active_requests: number; throughput_rps: number; errors: number; overload_rejections: number; stream_aborts: number; max_concurrency: number;
  latency_ms: { p50: number; p95: number; p99: number; sample_count: number };
  actions: Record<string, number>; tier_counts: Record<string, number>; detector_calls: Record<string, number>; detector_avg_latency_ms: Record<string, number>;
  config: { max_concurrency: number; queue_timeout_ms: number; upstream_timeout_s: number; upstream_retries: number };
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
  playground: (body: { prompt: string; context?: string; model?: string; use_case?: string }) =>
    fetch(`${API_BASE}/v1/oversight/playground`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    }).then((r) => r.json() as Promise<PlaygroundResult>),
  conformal: () => jget<{ axis: string; source?: string; risk_definition?: string; assumption?: string; certificates: { alpha: number; valid: boolean; tau: number; empirical_fnr: number; risk_bound: number; n_failures: number; holdout_fnr?: number | null; statement: string }[] }>("/v1/oversight/conformal"),
  generatePolicy: (spec: UseCaseSpec, apply = false) =>
    fetch(`${API_BASE}/v1/oversight/policy/generate?apply=${apply ? 1 : 0}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec),
    }).then((r) => r.json() as Promise<GeneratedPolicy>),
  startBenchmark: (n: number, weekly: number) =>
    jpost<JobSnapshot>(`/v1/oversight/jobs/benchmark?n=${n}&weekly_volume=${weekly}`),
  job: (id: string) => jget<JobSnapshot>(`/v1/oversight/jobs/${id}`),
  streamUrl: () => `${API_BASE}/v1/oversight/stream`,
  observability: () => jget<RuntimeObservability>('/v1/oversight/observability'),
  ready: () => jget<{ ready: boolean; upstream: string; policy_loaded: boolean; recorder: boolean; warmup: WarmupStatus }>('/readyz'),
  runtimeProbe: (n = 120, concurrency = 16) => jpost<JobSnapshot>(`/v1/oversight/jobs/runtime-probe?n=${n}&concurrency=${concurrency}`),
  verifyReceipt: (id: string) => jget<{ request_id: string; receipt_valid: boolean; chain_valid: boolean; hash_self: string; hash_prev: string }>(`/v1/oversight/receipts/${encodeURIComponent(id)}/verify`),
  cache: () => jget<CacheStatus>('/v1/oversight/cache'),
  informativeness: () => jget<InformativenessStatus>('/v1/oversight/informativeness'),
};
