// Shapes returned by the OpsMind backend (/v1/...). Only fields the UI reads are typed.

export type Decision = "APPROVED" | "MODIFIED" | "REJECTED" | "EXECUTE_MANUALLY";

export interface TraceEntry {
  step: string;
  status: "ok" | "warning" | "error" | "waiting";
  summary: string;
  details: string[];
  ts: string;
}

export interface Memory {
  id: string;
  text: string;
  score: number;
  document_id: string | null;
  metadata: Record<string, string>;
}

export interface Metrics {
  p95_seconds?: number | null;
  cache_hit_ratio?: number | null;
  redis_memory_utilization?: number | null;
  error_rate?: number | null;
}

export interface ExecutionRun {
  mode: string;
  is_success: boolean;
  duration_seconds: number;
  command: string[];
  output_tail: string;
  result: Record<string, unknown> | null;
}

export interface IncidentState {
  service: string;
  title: string;
  severity: string;
  findings?: string[];
  tool_errors?: string[];
  trace?: TraceEntry[];
  historical_memories?: Memory[];
  memory_status?: string;
  memory_guidance?: { matched_incidents: string[]; operator_comments: string[] };
  diagnosis?: { root_cause: string; category: string; rationale: string; evidence: string[] };
  diagnosis_engine?: { engine: string; provider?: string; model?: string; fallback_reason?: string };
  confidence?: number;
  recommended_runbook?: string | null;
  recommended_params?: Record<string, unknown>;
  risk?: string | null;
  policy?: { reasons: string[] };
  human_decision?: { decision: Decision; operator: string; comment: string; decided_at: string };
  final_action?: { runbook_id: string; params: Record<string, unknown>; risk: string } | null;
  execution_result?: { is_success: boolean; check: ExecutionRun | null; apply: ExecutionRun | null; error?: string };
  verification_result?: { outcome: string; before: Metrics; after: Metrics; verdict: { checks: Record<string, boolean> } };
  learning_summary?: string;
  memory_retained?: boolean;
}

export interface IncidentSummary {
  id: string;
  service: string;
  severity: string;
  title: string;
  status: string;
  created_at: string;
  category: string | null;
  confidence: number | null;
  recommended_runbook: string | null;
  final_runbook: string | null;
  decision: Decision | null;
  historical_matches: string[];
}

export interface Incident extends IncidentSummary {
  state: IncidentState;
}

export interface RunbookParam {
  type: "integer" | "string" | "boolean";
  default?: unknown;
  min?: number;
  max?: number;
  enum?: string[];
  description?: string;
}

export interface Runbook {
  id: string;
  title: string;
  risk: string;
  category: string;
  description: string;
  parameters: Record<string, RunbookParam>;
}

export interface Strategy {
  runbook_id: string;
  proposed: number;
  approved: number;
  modified: number;
  rejected: number;
  adopted: number;
  succeeded: number;
  failed: number;
  score: number | null;
}
