import { useState } from "react";

import { api } from "../api";
import { Badge } from "../components/Badge";
import { MemoryList } from "../components/Panels";
import { riskTone } from "../lib/format";
import { usePolling } from "../lib/usePolling";
import type { Memory } from "../types";

const REFRESH_MS = 10_000;
const DEFAULT_QUERY = "product-api cache saturation remediation operator feedback";

/** What OpsMind has learned: Hindsight memory search + strategy scores + the runbook catalog. */
export function KnowledgePage() {
  const strategies = usePolling(api.strategies, REFRESH_MS);
  const runbooks = usePolling(api.runbooks, REFRESH_MS, () => false);
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [memories, setMemories] = useState<Memory[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    try {
      setMemories(await api.memories(query));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main>
      <h1>Learning history</h1>
      <section className="card">
        <h3>Strategy scores <span className="muted">(succeeded ÷ (proposed + adopted))</span></h3>
        <table>
          <thead>
            <tr><th>Runbook</th><th>Proposed</th><th>Approved</th><th>Modified</th><th>Rejected</th><th>Adopted</th><th>Succeeded</th><th>Failed</th><th>Score</th></tr>
          </thead>
          <tbody>
            {(strategies.data ?? []).map((s) => (
              <tr key={s.runbook_id}>
                <td><code>{s.runbook_id}</code></td><td>{s.proposed}</td><td>{s.approved}</td><td>{s.modified}</td>
                <td>{s.rejected}</td><td>{s.adopted}</td><td>{s.succeeded}</td><td>{s.failed}</td>
                <td><strong>{s.score === null ? "—" : s.score.toFixed(2)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h3>Search Hindsight memory</h3>
        <form onSubmit={search} className="row">
          <input className="grow" aria-label="memory query" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button className="primary" type="submit">Recall</button>
        </form>
        {error && <p className="error">{error}</p>}
        {memories && <MemoryList memories={memories} emptyText="Nothing retained yet." />}
      </section>
      <section className="card">
        <h3>Runbook catalog <span className="muted">(the only actions the AI may propose)</span></h3>
        <ul className="runbooks">
          {(runbooks.data ?? []).map((r) => (
            <li key={r.id}>
              <code>{r.id}</code> <strong>{r.title}</strong> <Badge tone={riskTone(r.risk)}>{r.risk}</Badge>
              <p className="muted">{r.description}</p>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
