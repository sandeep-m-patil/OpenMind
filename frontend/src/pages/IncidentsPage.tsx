import { Link } from "react-router-dom";

import { api } from "../api";
import { Badge } from "../components/Badge";
import { formatPercent, formatTime, humanize, statusTone } from "../lib/format";
import { usePolling } from "../lib/usePolling";

const REFRESH_MS = 4000;

export function IncidentsPage() {
  const { data: incidents, error } = usePolling(api.incidents, REFRESH_MS);
  return (
    <main>
      <h1>Incidents</h1>
      {error && <p className="error">Backend unavailable: {error}</p>}
      {incidents && incidents.length === 0 && (
        <p className="muted">No incidents yet. Inject one with <code>create_incident.py --type cache</code> while load is running.</p>
      )}
      {incidents && incidents.length > 0 && (
        <table className="incidents">
          <thead>
            <tr>
              <th>Incident</th><th>Opened</th><th>Service</th><th>Diagnosis</th><th>Confidence</th>
              <th>Memory</th><th>Recommended → final</th><th>Decision</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((i) => (
              <tr key={i.id}>
                <td><Link to={`/incidents/${i.id}`}>{i.id}</Link></td>
                <td>{formatTime(i.created_at)}</td>
                <td>{i.service}</td>
                <td>{humanize(i.category)}</td>
                <td>{i.confidence !== null ? formatPercent(i.confidence) : "—"}</td>
                <td>{i.historical_matches.length ? `↺ ${i.historical_matches.join(", ")}` : "—"}</td>
                <td><code>{i.recommended_runbook ?? "—"}</code>{i.final_runbook && i.final_runbook !== i.recommended_runbook && <> → <code>{i.final_runbook}</code></>}</td>
                <td>{humanize(i.decision)}</td>
                <td><Badge tone={statusTone(i.status)}>{humanize(i.status)}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
