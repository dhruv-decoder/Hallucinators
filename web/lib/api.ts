// Typed client for the ControlPlane oversight API (FastAPI backend).
// In dev, calls go to /api/* which next.config rewrites to the backend (no CORS hop). In prod, set
// NEXT_PUBLIC_API_BASE to the deployed backend origin (CORS is enabled server-side).

import { API_BASE } from "./config";
import { authHeaders, streamAuthParams } from "./auth";
export { API_BASE };

export type Axis = "performance" | "cost" | "responsibility";
export type Action = "pass" | "annotate" | "auto_repair" | "escalate" | "block";

export interface AxisOutcome { p_fail: number }
export interface Signal {
  name: string; axis: Axis; tier: number; score: number; p_fail?: number; latency_ms?: number;
  detail?: Record<string, any>;
}
export interface VoIStep { axis: Axis; detector: string; tier: number; voi: number; check_cost: number; ran: boolean; reason: string }
export interface Pnl { cost_saved_usd: number; safety_spend_usd: number; net_usd: number }
// The text behind a decision, redacted server-side before it is written to the audit log. Without this a
// receipt is unreadable: you cannot tell whether "p_fail 0.98 -> repair" was right without seeing the words.
export interface Transcript {
  prompt: string; response: string; delivered: string;
  retrieved_context: string[]; model: string; redacted: Record<string, number>; truncated: boolean;
}
export interface Receipt {
  request_id: string; use_case: string; action: Action; policy_id: string; stopping_reason: string;
  ts?: string; transcript?: Transcript;
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
  active_policy: string; policies: Record<string, string>; builtin_policies?: string[]; models: { groundedness: string; pii: string; safety?: string; judge: string };
  savings_breakdown?: { route_down: number; cache: number; early_abort: number };
  spend_breakdown?: Record<string, number>;
}
export interface StreamGuardStep { text: string; action: "emit" | "hold" | "release" | "abort"; probe: number }
export interface StreamGuardCase {
  label: string; prompt: string; response: string; steps: StreamGuardStep[];
  aborted: boolean; emitted: string; tokens_emitted: number; tokens_withheld: number; final_probe: number; final_action: string;
}
export interface StreamGuardDemo { block_threshold: number; note: string; cases: StreamGuardCase[] }
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
export interface BenchmarkConfusion {
  precision: number; recall: number; f1: number; f1_ci_low?: number; f1_ci_high?: number;
  fpr: number; fnr: number; tp: number; fp: number; tn: number; fn: number;
}
export interface BenchmarkStrategy {
  name: string; n: number; errors: number;
  expensive_checks_run: number; expensive_checks_skipped: number; t0_clearance_pct: number;
  latency_ms: { mean: number; p50: number; p95: number; p99: number; samples: number };
  confusion: { performance: BenchmarkConfusion; responsibility: BenchmarkConfusion };
}
export interface BenchmarkEval {
  artifact?: string;
  methodology: {
    axes: string[]; n_requested: number; warmup_samples_excluded: number; latency_repeats: number;
    confusion_passes: number; tau: number; same_examples: boolean; models: boolean;
    cold_start_excluded_from_latency: boolean; note: string; fixed_checks_note?: string;
  };
  strategies: Record<string, BenchmarkStrategy>;
}
export interface VoICase {
  prompt: string; response: string; p_fail_after_t0: number; final_p_fail: number; action: Action;
  bought_a_check: boolean; stopping_reason: string;
  expensive_checks: { detector: string; tier: number; ran: boolean; p_fail_before: number; voi: number; check_cost: number; reason: string }[];
}
export interface VoIContrast { policy_id: string; safe: VoICase; uncertain: VoICase; note: string }
export interface RuntimeObservability {
  uptime_seconds: number; requests: number; active_requests: number; throughput_rps: number; errors: number; overload_rejections: number; stream_aborts: number; max_concurrency: number;
  latency_ms: { p50: number; p95: number; p99: number; sample_count: number };
  actions: Record<string, number>; tier_counts: Record<string, number>; detector_calls: Record<string, number>; detector_avg_latency_ms: Record<string, number>;
  config: { max_concurrency: number; queue_timeout_ms: number; upstream_timeout_s: number; upstream_retries: number };
}

export interface CacheDemoCall {
  cache_hit: boolean; kind: string; latency_ms: number;
  upstream_calls_before: number; upstream_calls_after: number; reached_the_model: boolean;
  input_tokens: number; output_tokens: number; response: string;
}
export interface CacheDemo {
  prompt: string; context: string; model: string; calls: CacheDemoCall[];
  identical_response: boolean; model_cost_avoided_usd: number; latency_saved_ms: number;
  cache: CacheStatus; note: string;
}

export interface HardCaseFamily {
  id: string; source: string; why: string;
  cases: number; runs: number; model_failed: number; caught: number; flagged_safe: number;
}
export interface HardCase {
  id: string; family: string; note: string; prompt: string; context: string;
  runs: number; model_failed: number; oversight_caught: number; flagged_when_model_was_right: number;
  actions: Record<string, number>; example_response: string; shipped: boolean;
}
export interface HardCases {
  artifact?: string; generated_at: string; model: string; repeats_per_case: number; decoding: string;
  method: string; families: HardCaseFamily[]; cases: HardCase[];
  totals: { cases: number; runs: number; model_failures: number; caught: number; flagged_when_model_was_right: number; shipped: number };
  caveats: string[];
}

export interface EstimateStep {
  metric: string; value: string; formula: string; inputs: string[]; meaning: string;
  latex?: string; latex_substituted?: string;
}
export interface EstimateMethod {
  basis: string; constants: Record<string, any>; steps: EstimateStep[]; caveats: string[];
}

export interface GeneratedPolicy {
  profile_id: string; applied: boolean;
  knobs: { lambda_latency: number; cost_fail: Record<string, number>; block_threshold: number; escalate_threshold: number; annotate_threshold: number };
  projection: {
    weekly_volume: number; cleared_at_t0_pct: number; added_latency_p95_ms: number; escalation_rate: number;
    human_reviews_per_month: number; projected_monthly_net_usd: number; self_funding: boolean; note: string;
    estimate_method?: EstimateMethod;
  };
  rationale: string[]; recommended_detectors: string[]; compliance: string[];
}

// Every call carries the caller's workspace headers so the backend routes it to the right isolated service.
function jheaders(extra?: Record<string, string>): Record<string, string> {
  return { ...authHeaders(), ...(extra ?? {}) };
}
async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { headers: jheaders() });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
async function jpost<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { method: "POST", headers: jheaders() });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  health: () => jget<{ ok: boolean; upstream: string; models: Summary["models"] }>("/healthz"),
  summary: () => jget<Summary>("/v1/oversight/summary"),
  receipts: (limit = 80) => jget<{ receipts: Receipt[] }>(`/v1/oversight/receipts?limit=${limit}`),
  simulate: () =>
    jpost<{ processed: number; results: { request_id: string; action: Action }[] }>("/v1/oversight/simulate"),
  reset: () => jpost<{ reset: boolean; cleared_receipts: number; dropped_policies: string[] }>("/v1/oversight/reset"),
  setPolicy: (policy: string) =>
    fetch(`${API_BASE}/v1/oversight/policy`, {
      method: "POST", headers: jheaders({ "content-type": "application/json" }), body: JSON.stringify({ policy }),
    }).then((r) => r.json()),
  replay: () => jpost<{ scenarios: Scenario[] }>("/v1/oversight/replay"),
  agentDemo: () => jpost<AgentReceipt>("/v1/oversight/agent-demo"),
  compliance: () => jget<{ decisions: number; controls: ControlRow[] }>("/v1/oversight/compliance"),
  playground: (body: { prompt: string; context?: string; model?: string; use_case?: string }) =>
    fetch(`${API_BASE}/v1/oversight/playground`, {
      method: "POST", headers: jheaders({ "content-type": "application/json" }), body: JSON.stringify(body),
    }).then((r) => r.json() as Promise<PlaygroundResult>),
  conformal: () => jget<{ axis: string; source?: string; risk_definition?: string; assumption?: string; certificates: { alpha: number; valid: boolean; tau: number; empirical_fnr: number; risk_bound: number; n_failures: number; holdout_fnr?: number | null; statement: string }[] }>("/v1/oversight/conformal"),
  generatePolicy: (spec: UseCaseSpec, apply = false) =>
    fetch(`${API_BASE}/v1/oversight/policy/generate?apply=${apply ? 1 : 0}`, {
      method: "POST", headers: jheaders({ "content-type": "application/json" }), body: JSON.stringify(spec),
    }).then((r) => r.json() as Promise<GeneratedPolicy>),
  startBenchmark: (n: number, weekly: number) =>
    jpost<JobSnapshot>(`/v1/oversight/jobs/benchmark?n=${n}&weekly_volume=${weekly}`),
  job: (id: string) => jget<JobSnapshot>(`/v1/oversight/jobs/${id}`),
  streamUrl: () => `${API_BASE}/v1/oversight/stream${streamAuthParams()}`,
  observability: () => jget<RuntimeObservability>('/v1/oversight/observability'),
  ready: () => jget<{ ready: boolean; upstream: string; policy_loaded: boolean; recorder: boolean; warmup: WarmupStatus }>('/readyz'),
  runtimeProbe: (n = 120, concurrency = 16) => jpost<JobSnapshot>(`/v1/oversight/jobs/runtime-probe?n=${n}&concurrency=${concurrency}`),
  verifyReceipt: (id: string) => jget<{ request_id: string; receipt_valid: boolean; chain_valid: boolean; hash_self: string; hash_prev: string }>(`/v1/oversight/receipts/${encodeURIComponent(id)}/verify`),
  override: (request_id: string, is_failure: boolean, axis = "performance") =>
    fetch(`${API_BASE}/v1/oversight/override`, {
      method: "POST", headers: jheaders({ "content-type": "application/json" }), body: JSON.stringify({ request_id, is_failure, axis }),
    }).then((r) => r.json() as Promise<{ recorded: boolean; detectors_refit: string[]; feedback_counts: Record<string, number>; threshold: number }>),
  cache: () => jget<CacheStatus>('/v1/oversight/cache'),
  informativeness: () => jget<InformativenessStatus>('/v1/oversight/informativeness'),
  benchmark: () => jget<BenchmarkEval>('/v1/oversight/benchmark'),
  hardCases: () => jget<HardCases>('/v1/oversight/hard-cases'),
  cacheDemo: () => jpost<CacheDemo>('/v1/oversight/cache-demo'),
  voiContrast: () => jget<VoIContrast>('/v1/oversight/voi-contrast'),
  streamGuard: () => jget<StreamGuardDemo>('/v1/oversight/streamguard-demo'),
};
