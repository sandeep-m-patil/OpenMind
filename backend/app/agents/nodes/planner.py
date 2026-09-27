"""Node 5 — Runbook Planner + risk/policy gate. Code validates whatever the LLM chose."""
from app.agents import rules
from app.agents.deps import AgentDeps
from app.agents.memory_guidance import overruled_ids
from app.agents.state import IncidentState, trace


def make_planner(deps: AgentDeps):
    def planner(state: IncidentState) -> dict:
        diagnosis = state["diagnosis"]
        guidance = state.get("memory_guidance", {})
        runbook_id, params = diagnosis.get("recommended_runbook"), diagnosis.get("runbook_params") or {}
        notes: list[str] = []
        if runbook_id is not None and not deps.catalog.has(runbook_id):
            notes.append(f"Rejected invalid runbook {runbook_id!r} from the model; using rule-engine choice.")
            runbook_id, _ = rules.choose_runbook(diagnosis.get("category", "unknown"), guidance)
            params = {}
        policy = deps.policy.evaluate(runbook_id, params, overruled_ids(guidance))
        if runbook_id and not policy.is_allowed:
            notes.append(f"Policy rejected parameters ({'; '.join(policy.reasons)}); using runbook defaults.")
            policy = deps.policy.evaluate(runbook_id, {}, overruled_ids(guidance))
        scores = {s["runbook_id"]: s for s in state.get("strategy_scores", [])}
        if runbook_id in scores and scores[runbook_id]["score"] is not None:
            notes.append(f"Strategy score for {runbook_id}: {scores[runbook_id]['score']:.2f}")
        title = deps.catalog.get(runbook_id).title if policy.is_allowed else "manual investigation"
        summary = f"Proposed {runbook_id} ({title}), risk {policy.risk}" if policy.is_allowed else \
            "No safe automated runbook — human must choose"
        return {
            "recommended_runbook": runbook_id if policy.is_allowed else None,
            "recommended_params": policy.params,
            "risk": policy.risk,
            "policy": policy.to_dict(),
            "status": "PENDING_APPROVAL",
            "trace": trace("planner", summary, notes + policy.reasons, "ok" if policy.is_allowed else "warning")
                     + trace("approval", "Waiting for human decision (Approve / Edit / Reject / Execute manually)",
                             status="waiting"),
        }

    return planner
