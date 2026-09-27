import { useState } from "react";

import type { DecisionPayload } from "../api";
import type { Decision, Runbook } from "../types";

const OPERATOR_KEY = "opsmind.operator";

function storedOperator(): string {
  try {
    return localStorage.getItem(OPERATOR_KEY) ?? "";
  } catch {
    return "";
  }
}

interface Props {
  recommended: string | null | undefined;
  recommendedParams: Record<string, unknown>;
  runbooks: Runbook[];
  onDecide: (payload: DecisionPayload) => Promise<void>;
}

/** Approve / Edit / Reject / Execute manually. The backend re-validates every choice. */
export function DecisionPanel({ recommended, recommendedParams, runbooks, onDecide }: Props) {
  const [operator, setOperator] = useState(storedOperator);
  const [comment, setComment] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [runbookId, setRunbookId] = useState(recommended ?? runbooks[0]?.id ?? "");
  const [params, setParams] = useState<Record<string, unknown>>(recommendedParams);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const selected = runbooks.find((r) => r.id === runbookId);

  async function submit(decision: Decision) {
    if (!operator.trim()) return setError("Enter your name first — decisions are attributed.");
    try {
      localStorage.setItem(OPERATOR_KEY, operator);
    } catch {
      /* storage unavailable: not important */
    }
    setIsBusy(true);
    setError(null);
    const payload: DecisionPayload = { decision, operator, comment };
    if (decision === "MODIFIED") Object.assign(payload, { runbook_id: runbookId, params });
    try {
      await onDecide(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section className="card decision" aria-label="Human decision">
      <h3>Your decision</h3>
      <div className="row">
        <label>
          Operator
          <input value={operator} onChange={(e) => setOperator(e.target.value)} placeholder="your name" />
        </label>
        <label className="grow">
          Comment (retained in memory)
          <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="why? e.g. only remove stale session keys" />
        </label>
      </div>
      {isEditing && (
        <div className="row edit">
          <label>
            Runbook
            <select value={runbookId} onChange={(e) => { setRunbookId(e.target.value); setParams({}); }}>
              {runbooks.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} — {r.title} ({r.risk})
                </option>
              ))}
            </select>
          </label>
          {selected &&
            Object.entries(selected.parameters).map(([name, spec]) => (
              <label key={name}>
                {name}
                <input
                  aria-label={name}
                  value={String(params[name] ?? spec.default ?? "")}
                  onChange={(e) => setParams({ ...params, [name]: spec.type === "integer" ? Number(e.target.value) : e.target.value })}
                />
              </label>
            ))}
        </div>
      )}
      <div className="buttons">
        <button className="primary" disabled={isBusy || !recommended} onClick={() => submit("APPROVED")}>Approve</button>
        {isEditing ? (
          <button className="primary" disabled={isBusy} onClick={() => submit("MODIFIED")}>Submit edited action</button>
        ) : (
          <button disabled={isBusy} onClick={() => setIsEditing(true)}>Edit</button>
        )}
        <button className="danger" disabled={isBusy} onClick={() => submit("REJECTED")}>Reject</button>
        <button disabled={isBusy} onClick={() => submit("EXECUTE_MANUALLY")}>Execute manually</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
