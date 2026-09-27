"""Node 6 — Human Approval. The graph STOPS here (LangGraph interrupt) until a human decides.

The decision arrives already validated (see services/decisions.py): the final action passed the
policy gate again, so a human edit can't smuggle in an unknown runbook or out-of-range parameter.
"""
from langgraph.types import interrupt

from app.agents.deps import AgentDeps
from app.agents.state import IncidentState, trace

NEXT_STATUS = {
    "APPROVED": "EXECUTING",
    "MODIFIED": "EXECUTING",
    "EXECUTE_MANUALLY": "AWAITING_MANUAL_EXECUTION",
    "REJECTED": "REJECTED",
}


def _summary(decision: dict, recommended: str | None) -> str:
    final = (decision.get("final_action") or {}).get("runbook_id")
    who, kind = decision["operator"], decision["decision"]
    if kind == "MODIFIED":
        return f"{who} MODIFIED the recommendation: {recommended} → {final} {decision['final_action']['params']}"
    if kind == "APPROVED":
        return f"{who} APPROVED {final}"
    if kind == "REJECTED":
        return f"{who} REJECTED {recommended}"
    return f"{who} will EXECUTE MANUALLY ({final or 'own action'}); OpsMind will verify"


def make_approval(_: AgentDeps):
    def approval(state: IncidentState) -> dict:
        decision = interrupt({
            "incident_id": state["incident_id"],
            "recommended_runbook": state.get("recommended_runbook"),
            "params": state.get("recommended_params"),
            "risk": state.get("risk"),
        })
        details = [f"Comment: {decision['comment']}"] if decision.get("comment") else []
        return {
            "human_decision": decision,
            "final_action": decision.get("final_action"),
            "status": NEXT_STATUS[decision["decision"]],
            "trace": trace("approval", _summary(decision, state.get("recommended_runbook")), details),
        }

    return approval


def route_after_approval(state: IncidentState) -> str:
    return {"APPROVED": "execution", "MODIFIED": "execution",
            "EXECUTE_MANUALLY": "verification"}.get(state["human_decision"]["decision"], "learning")
