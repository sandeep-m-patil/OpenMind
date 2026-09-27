import { useCallback } from "react";
import { useParams } from "react-router-dom";

import { api, type DecisionPayload } from "../api";
import { DecisionPanel } from "../components/DecisionPanel";
import { KeyFacts } from "../components/KeyFacts";
import { ExecutionPanel, MemoryList, VerificationPanel } from "../components/Panels";
import { Timeline } from "../components/Timeline";
import { TERMINAL_STATUSES } from "../lib/format";
import { usePolling } from "../lib/usePolling";
import type { Incident } from "../types";

const REFRESH_MS = 2500;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

export function IncidentPage() {
  const { id = "" } = useParams();
  const load = useCallback(() => api.incident(id), [id]);
  const incident = usePolling<Incident>(load, REFRESH_MS, (d) => !d || !TERMINAL_STATUSES.has(d.status));
  const runbooks = usePolling(api.runbooks, 60_000, () => false);

  if (incident.error) return <main><p className="error">{incident.error}</p></main>;
  if (!incident.data) return <main><p className="muted">Loading {id}…</p></main>;
  const { state, status } = incident.data;

  async function decide(payload: DecisionPayload) {
    await api.decide(id, payload);
    incident.reload();
  }

  return (
    <main className="incident">
      <KeyFacts incident={incident.data} />
      {status === "PENDING_APPROVAL" && (
        <DecisionPanel recommended={state.recommended_runbook} recommendedParams={state.recommended_params ?? {}}
                       runbooks={runbooks.data ?? []} onDecide={decide} />
      )}
      <div className="columns">
        <div>
          <Section title="Agent trace"><Timeline trace={state.trace ?? []} /></Section>
        </div>
        <div>
          <Section title="Evidence">
            <ul>{(state.findings ?? []).map((f) => <li key={f}>{f}</li>)}</ul>
            {(state.tool_errors ?? []).map((e) => <p key={e} className="error">⚠ {e}</p>)}
          </Section>
          <Section title="Hindsight memory recalled">
            <MemoryList memories={state.historical_memories ?? []}
                        emptyText={state.memory_status && state.memory_status !== "ok" ? `Hindsight ${state.memory_status}` : "No similar past incidents."} />
          </Section>
          {state.diagnosis && (
            <Section title="AI diagnosis">
              <p>{state.diagnosis.root_cause}</p>
              <p className="muted">{state.diagnosis.rationale}</p>
              <p className="muted">
                Engine: {state.diagnosis_engine?.engine === "llm" ? `${state.diagnosis_engine.provider} / ${state.diagnosis_engine.model}` : "rule engine"}
              </p>
            </Section>
          )}
          {state.policy && (
            <Section title="Runbook & policy gate">
              <ul>{state.policy.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </Section>
          )}
          {state.execution_result && <Section title="Execution (Ansible)"><ExecutionPanel result={state.execution_result} /></Section>}
          {state.verification_result && <Section title="Verification"><VerificationPanel result={state.verification_result} /></Section>}
        </div>
      </div>
    </main>
  );
}
