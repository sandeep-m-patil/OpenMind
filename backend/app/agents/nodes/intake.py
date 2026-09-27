"""Node 1 — Incident Intake: normalize the alert into symptoms."""
from app.agents.deps import AgentDeps
from app.agents.state import IncidentState, trace


def make_intake(_: AgentDeps):
    def intake(state: IncidentState) -> dict:
        alert = state.get("alert") or {}
        annotations = alert.get("annotations") or {}
        symptoms = list(dict.fromkeys(
            [s for s in [annotations.get("summary"), annotations.get("description")] if s] + state.get("symptoms", [])
        )) or [state.get("title", "unspecified problem")]
        source = f"alert {alert['labels'].get('alertname')}" if alert.get("labels") else "manual trigger"
        return {
            "symptoms": symptoms,
            "status": "INVESTIGATING",
            "trace": trace("intake", f"Incident received from {source}: {state.get('title')}", symptoms),
        }

    return intake
