"""Validate a human decision into a final action BEFORE resuming the graph (so bad input → HTTP 4xx)."""
from datetime import datetime, timezone

from app.agents.memory_guidance import overruled_ids
from app.schemas.decisions import DecisionIn
from app.services.policy import PolicyGate


class DecisionError(ValueError):
    pass


def resolve_decision(decision: DecisionIn, state: dict, policy: PolicyGate) -> dict:
    recommended = state.get("recommended_runbook")
    base = {"decision": decision.decision, "operator": decision.operator, "comment": decision.comment,
            "decided_at": datetime.now(timezone.utc).isoformat(), "final_action": None}
    if decision.decision == "REJECTED":
        return base
    if decision.decision == "MODIFIED":
        runbook_id = decision.runbook_id or recommended
        params = decision.params if decision.params is not None else (
            state.get("recommended_params", {}) if runbook_id == recommended else {})
    else:
        runbook_id, params = recommended, state.get("recommended_params", {})
    if runbook_id is None:
        if decision.decision == "EXECUTE_MANUALLY":
            return base  # human acts outside OpsMind; we still verify and learn
        raise DecisionError("no recommended runbook to approve — use MODIFIED with a runbook_id")
    result = policy.evaluate(runbook_id, params, overruled_ids(state.get("memory_guidance", {})))
    if not result.is_allowed:
        raise DecisionError("; ".join(result.reasons))
    return {**base, "final_action": {"runbook_id": runbook_id, "params": result.params, "risk": result.risk}}
