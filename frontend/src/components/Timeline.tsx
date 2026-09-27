import { formatTime } from "../lib/format";
import type { TraceEntry } from "../types";

const ICON: Record<TraceEntry["status"], string> = { ok: "✓", warning: "!", error: "✕", waiting: "⏸" };

/** The agent's trace: concise operational reasoning, never hidden chain-of-thought. */
export function Timeline({ trace }: { trace: TraceEntry[] }) {
  return (
    <ol className="timeline">
      {trace.map((entry, index) => (
        <li key={`${entry.step}-${index}`} className={`step step-${entry.status}`}>
          <span className="step-icon" aria-hidden>
            {ICON[entry.status]}
          </span>
          <div>
            <div className="step-head">
              <strong>{entry.step}</strong>
              <time className="muted">{formatTime(entry.ts)}</time>
            </div>
            <p>{entry.summary}</p>
            {entry.details.length > 0 && (
              <ul className="details">
                {entry.details.map((detail, i) => (
                  <li key={i}>{detail}</li>
                ))}
              </ul>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
