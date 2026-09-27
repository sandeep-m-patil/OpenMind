import { Link } from "react-router-dom";

import { formatLatency, formatPercent, humanize, riskTone, statusTone } from "../lib/format";
import type { Incident } from "../types";
import { Badge } from "./Badge";

/** The one-glance incident summary: problem → diagnosis → memory → decision → result → lesson. */
export function KeyFacts({ incident }: { incident: Incident }) {
  const s = incident.state;
  const verification = s.verification_result;
  const rows: [string, React.ReactNode][] = [
    ["Problem", s.title],
    ["AI diagnosis", s.diagnosis ? humanize(s.diagnosis.category) : "investigating…"],
    ["Confidence", s.confidence !== undefined ? formatPercent(s.confidence) : "—"],
    [
      "Historical incidents",
      incident.historical_matches.length ? (
        incident.historical_matches.map((id) => (
          <Link key={id} to={`/incidents/${id}`} className="chip">
            {id}
          </Link>
        ))
      ) : (
        <span className="muted">none in memory yet</span>
      ),
    ],
    [
      "Recommended runbook",
      s.recommended_runbook ? (
        <>
          <code>{s.recommended_runbook}</code> <Badge tone={riskTone(s.risk)}>{s.risk} risk</Badge>
        </>
      ) : (
        "—"
      ),
    ],
    ["Human decision", s.human_decision ? `${humanize(s.human_decision.decision)} by ${s.human_decision.operator}` : "pending"],
    ["Final action", s.final_action ? <code>{s.final_action.runbook_id}</code> : "—"],
    ["Result", <Badge tone={statusTone(incident.status)}>{humanize(incident.status)}</Badge>],
    [
      "P95 latency",
      verification ? `${formatLatency(verification.before.p95_seconds)} → ${formatLatency(verification.after.p95_seconds)}` : "—",
    ],
  ];
  return (
    <section className="card keyfacts" aria-label="Incident summary">
      <h2>
        {incident.id} <span className="muted">· {incident.service}</span>
      </h2>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label} className="fact">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {s.learning_summary && (
        <p className="lesson">
          <strong>🧠 Learned:</strong> {s.learning_summary}
        </p>
      )}
    </section>
  );
}
