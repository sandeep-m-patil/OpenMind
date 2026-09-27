import { vi } from "vitest";

import type { Incident, Runbook, Strategy } from "../types";

export const RUNBOOKS: Runbook[] = [
  { id: "RB-CACHE-001", title: "Targeted stale-session cache cleanup", risk: "LOW", category: "cache_saturation",
    description: "only stale", parameters: { max_idle_hours: { type: "integer", default: 24, min: 1, max: 720 } } },
  { id: "RB-CACHE-002", title: "Full cache flush", risk: "HIGH", category: "cache_saturation", description: "flush", parameters: {} },
];

export const STRATEGIES: Strategy[] = [
  { runbook_id: "RB-CACHE-001", proposed: 1, approved: 1, modified: 0, rejected: 0, adopted: 1, succeeded: 2, failed: 0, score: 1 },
];

export function incident(overrides: Partial<Incident> = {}, state: Partial<Incident["state"]> = {}): Incident {
  return {
    id: "INC-1002", service: "product-api", severity: "critical", title: "High latency", status: "PENDING_APPROVAL",
    created_at: "2026-09-27T11:30:00Z", category: "cache_saturation", confidence: 0.92,
    recommended_runbook: "RB-CACHE-001", final_runbook: null, decision: null, historical_matches: ["INC-1001"],
    state: {
      service: "product-api", title: "High latency", severity: "critical", confidence: 0.92, risk: "LOW",
      findings: ["Redis memory is at 100% of its limit."], tool_errors: [],
      recommended_runbook: "RB-CACHE-001", recommended_params: { max_idle_hours: 24 },
      diagnosis: { root_cause: "Redis cache saturation", category: "cache_saturation", rationale: "INC-1001 was resolved", evidence: [] },
      diagnosis_engine: { engine: "rules" }, policy: { reasons: ["base risk of RB-CACHE-001 is LOW"] },
      memory_status: "ok",
      historical_memories: [{ id: "m1", text: "Operator rejected full flush", score: 1.1, document_id: "INC-1001",
                              metadata: { incident_id: "INC-1001", final_runbook: "RB-CACHE-001", decision: "MODIFIED" } }],
      trace: [{ step: "recall", status: "ok", summary: "Hindsight recalled 1 memories", details: ["INC-1001: resolved"], ts: "2026-09-27T11:30:05Z" },
              { step: "approval", status: "waiting", summary: "Waiting for human decision", details: [], ts: "2026-09-27T11:30:06Z" }],
      ...state,
    },
    ...overrides,
  };
}

export const RESOLVED_STATE: Partial<Incident["state"]> = {
  human_decision: { decision: "APPROVED", operator: "harinath", comment: "", decided_at: "2026-09-27T11:31:00Z" },
  final_action: { runbook_id: "RB-CACHE-001", params: { max_idle_hours: 24 }, risk: "LOW" },
  execution_result: {
    is_success: true,
    check: { mode: "check", is_success: true, duration_seconds: 2, command: [], output_tail: "ok", result: { sessions_stale: 19156 } },
    apply: { mode: "apply", is_success: true, duration_seconds: 4, command: [], output_tail: "ok", result: { sessions_deleted: 19156 } },
  },
  verification_result: {
    outcome: "RESOLVED", before: { p95_seconds: 7.59, cache_hit_ratio: 0.03, redis_memory_utilization: 1 },
    after: { p95_seconds: 0.273, cache_hit_ratio: 0.94, redis_memory_utilization: 0.06 },
    verdict: { checks: { p95_below_target: true, service_healthy: true } },
  },
  learning_summary: "RB-CACHE-001 resolved cache_saturation on product-api.",
};

/** Route fetch() calls by URL substring to canned envelope responses. */
export function mockApi(routes: Record<string, unknown>, calls: { url: string; body?: string }[] = []) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, body: init?.body as string | undefined });
    const key = Object.keys(routes).find((k) => url.includes(k));
    if (key === undefined) return new Response(JSON.stringify({ data: null, error: { message: "not found" } }), { status: 404 });
    const value = routes[key];
    if (value instanceof Error) return new Response(JSON.stringify({ data: null, error: { message: value.message } }), { status: 422 });
    return new Response(JSON.stringify({ data: value, meta: {}, error: null }), { status: 200 });
  });
}
