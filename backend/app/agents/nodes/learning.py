"""Node 9 — Learning: write the postmortem, RETAIN it in Hindsight, update strategy scores."""
from datetime import datetime, timezone

from app.agents.deps import AgentDeps
from app.agents.learning_record import build_record
from app.agents.state import IncidentState, trace
from app.services.memory import MemoryItem, MemoryUnavailable


def make_learning(deps: AgentDeps):
    def learning(state: IncidentState) -> dict:
        record = build_record(state)
        ctx = record["context"]
        item = MemoryItem(
            content=record["narrative"], context="SRE incident postmortem", document_id=ctx["incident_id"],
            metadata=record["metadata"], tags=record["tags"], timestamp=datetime.now(timezone.utc).isoformat(),
        )
        try:
            deps.memory.retain([item])
            is_retained, note = True, "Experience retained in Hindsight"
        except MemoryUnavailable as exc:
            is_retained, note = False, f"Hindsight unavailable, record kept in OpsMind DB only (retry later): {exc}"
        deps.strategies.record(recommended=ctx["recommended"], final=ctx["final"],
                               decision=ctx["decision"], outcome=ctx["outcome"])
        return {
            "outcome": ctx["outcome"], "status": ctx["outcome"],
            "learning_summary": record["lesson"], "learning_record": record, "memory_retained": is_retained,
            "trace": trace("learning", f"Learned: {record['lesson']}", [note], "ok" if is_retained else "warning"),
        }

    return learning
