"""Node 3 — Memory Recall: ask Hindsight for similar past incidents BEFORE diagnosing."""
from dataclasses import asdict

from app.agents.analysis import memory_query
from app.agents.deps import AgentDeps
from app.agents.memory_guidance import derive_guidance
from app.agents.state import IncidentState, trace
from app.services.memory import MemoryUnavailable


def _describe(guidance: dict) -> list[str]:
    lines = [f"{p['incident_id']}: resolved with {p['runbook']}" for p in guidance["preferred"]]
    lines += [f"{o['incident_id']}: operator overruled {o['runbook']}"
              + (f" → {o['replaced_by']}" if o["replaced_by"] else "")
              + (f" (\"{o['reason']}\")" if o["reason"] else "") for o in guidance["overruled"]]
    return lines


def make_recall(deps: AgentDeps):
    def recall(state: IncidentState) -> dict:
        query = memory_query(state["service"], state.get("title", ""), state.get("signals", {}))
        try:
            memories = [asdict(m) for m in deps.memory.recall(query, tags=[f"service:{state['service']}"])]
            status = "ok"
        except MemoryUnavailable as exc:
            memories, status = [], f"unavailable: {exc}"
        guidance = derive_guidance(memories)
        if status != "ok":
            entry = trace("recall", "Hindsight unavailable — continuing without history", [status], "warning")
        elif not memories:
            entry = trace("recall", "Hindsight recall: no similar past incidents yet", [query])
        else:
            entry = trace("recall", f"Hindsight recalled {len(memories)} memories "
                          f"({len(guidance['matched_incidents'])} past incidents)", _describe(guidance))
        return {"memory_query": query, "memory_status": status, "historical_memories": memories,
                "memory_guidance": guidance, "trace": entry}

    return recall
