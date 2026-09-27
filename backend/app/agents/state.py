"""Typed LangGraph state for one incident, plus the trace helper every node uses."""
import operator
from datetime import datetime, timezone
from typing import Annotated, Literal, TypedDict

TraceStatus = Literal["ok", "warning", "error", "waiting"]


class TraceEntry(TypedDict):
    step: str
    status: TraceStatus
    summary: str
    details: list[str]
    ts: str


class IncidentState(TypedDict, total=False):
    # intake
    incident_id: str
    service: str
    severity: str
    title: str
    alert: dict
    symptoms: list[str]
    status: str
    # evidence
    metrics: dict
    logs: dict
    health: dict
    recent_changes: list[dict]
    tool_errors: list[str]
    findings: list[str]
    signals: dict
    # memory
    memory_query: str
    memory_status: str
    historical_memories: list[dict]
    memory_guidance: dict
    # diagnosis + plan
    diagnosis: dict
    confidence: float
    evidence: list[str]
    diagnosis_engine: dict
    recommended_runbook: str | None
    recommended_params: dict
    risk: str | None
    policy: dict
    strategy_scores: list[dict]
    # human + execution
    human_decision: dict
    final_action: dict
    metrics_before: dict
    execution_result: dict
    verification_result: dict
    # learning
    outcome: str
    learning_summary: str
    learning_record: dict
    memory_retained: bool
    # append-only timeline (each node returns only its new entries)
    trace: Annotated[list[TraceEntry], operator.add]


def trace(step: str, summary: str, details: list[str] | None = None, status: TraceStatus = "ok") -> list[TraceEntry]:
    return [TraceEntry(step=step, status=status, summary=summary, details=details or [],
                       ts=datetime.now(timezone.utc).isoformat())]
