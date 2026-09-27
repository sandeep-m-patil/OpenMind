import { formatLatency, formatPercent } from "../lib/format";
import type { ExecutionRun, IncidentState, Memory } from "../types";

export function MemoryList({ memories, emptyText }: { memories: Memory[]; emptyText: string }) {
  if (!memories.length) return <p className="muted">{emptyText}</p>;
  return (
    <ul className="memories">
      {memories.map((m) => (
        <li key={m.id}>
          <div className="memory-head">
            <strong>{m.metadata.incident_id ?? m.document_id}</strong>
            <span className="muted">relevance {m.score.toFixed(2)}</span>
            {m.metadata.final_runbook && <code>{m.metadata.final_runbook}</code>}
            {m.metadata.decision && <span className="chip">{m.metadata.decision}</span>}
          </div>
          <p>{m.text}</p>
        </li>
      ))}
    </ul>
  );
}

function Run({ run }: { run: ExecutionRun }) {
  return (
    <div className="run">
      <p>
        <strong>{run.mode === "check" ? "Dry run (--check)" : "Apply"}</strong> — {run.is_success ? "ok" : "failed"} in {run.duration_seconds}s
      </p>
      {run.result && <pre>{JSON.stringify(run.result, null, 2)}</pre>}
      <details>
        <summary>Ansible output</summary>
        <pre>{run.output_tail}</pre>
      </details>
    </div>
  );
}

export function ExecutionPanel({ result }: { result: NonNullable<IncidentState["execution_result"]> }) {
  return (
    <div>
      {result.error && <p className="error">{result.error}</p>}
      {result.check && <Run run={result.check} />}
      {result.apply && <Run run={result.apply} />}
    </div>
  );
}

export function VerificationPanel({ result }: { result: NonNullable<IncidentState["verification_result"]> }) {
  const rows: [string, string, string][] = [
    ["P95 latency", formatLatency(result.before.p95_seconds), formatLatency(result.after.p95_seconds)],
    ["Cache hit ratio", formatPercent(result.before.cache_hit_ratio), formatPercent(result.after.cache_hit_ratio)],
    ["Redis memory", formatPercent(result.before.redis_memory_utilization), formatPercent(result.after.redis_memory_utilization)],
    ["Error rate", formatPercent(result.before.error_rate), formatPercent(result.after.error_rate)],
  ];
  return (
    <div>
      <table>
        <thead>
          <tr><th>Metric</th><th>Before</th><th>After</th></tr>
        </thead>
        <tbody>
          {rows.map(([name, before, after]) => (
            <tr key={name}><td>{name}</td><td>{before}</td><td>{after}</td></tr>
          ))}
        </tbody>
      </table>
      <ul className="checks">
        {Object.entries(result.verdict.checks).map(([check, passed]) => (
          <li key={check}>{passed ? "✓" : "✕"} {check.replace(/_/g, " ")}</li>
        ))}
      </ul>
    </div>
  );
}
