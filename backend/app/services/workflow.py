"""Runs the LangGraph workflow in background threads: start an incident, resume it with a decision."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from langgraph.types import Command

from app.agents.state import trace
from app.schemas.decisions import DecisionIn
from app.services.decisions import resolve_decision
from app.services.incident_store import IncidentStore
from app.services.policy import PolicyGate

logger = logging.getLogger("opsmind.workflow")
MAX_CONCURRENT_WORKFLOWS = 4
PENDING = "PENDING_APPROVAL"
DECISION_RECORDED = "DECISION_RECORDED"


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


class Notifier(Protocol):
    def incident_pending(self, incident: dict) -> None: ...
    def incident_finished(self, incident: dict) -> None: ...


class WorkflowRunner:
    def __init__(self, graph, incidents: IncidentStore, policy: PolicyGate, notifier: Notifier,
                 is_async: bool = True) -> None:
        self._graph, self._incidents, self._policy, self._notifier = graph, incidents, policy, notifier
        self._is_async = is_async
        self._threads = ThreadPoolExecutor(MAX_CONCURRENT_WORKFLOWS, thread_name_prefix="workflow")

    def open_incident(self, *, service: str, severity: str, title: str,
                      alert: dict | None = None, symptoms: list[str] | None = None) -> tuple[str, bool]:
        """Returns (incident_id, is_new). An open incident for the same service absorbs new alerts."""
        existing = self._incidents.find_open(service)
        if existing:
            return existing["id"], False
        initial = {"service": service, "severity": severity, "title": title, "alert": alert or {},
                   "symptoms": symptoms or [], "trace": []}
        incident_id = self._incidents.create(service, severity, title, initial)
        self._submit(incident_id, {**initial, "incident_id": incident_id})
        return incident_id, True

    def decide(self, incident_id: str, decision: DecisionIn) -> dict:
        row = self._incidents.get(incident_id)
        if row is None:
            raise NotFound(incident_id)
        if row["status"] != PENDING:
            raise Conflict(f"{incident_id} is {row['status']}, not {PENDING}")
        resolved = resolve_decision(decision, row["state"], self._policy)  # raises DecisionError
        if not self._incidents.claim_status(incident_id, PENDING, DECISION_RECORDED):
            raise Conflict(f"{incident_id} was decided by someone else")
        self._submit(incident_id, Command(resume=resolved))
        return resolved

    def _submit(self, incident_id: str, payload: Any) -> None:
        if self._is_async:
            self._threads.submit(self._run, incident_id, payload)
        else:
            self._run(incident_id, payload)

    def _run(self, incident_id: str, payload: Any) -> None:
        config = {"configurable": {"thread_id": incident_id}}
        try:
            result = self._graph.invoke(payload, config)
            row = self._incidents.get(incident_id)
            if "__interrupt__" in result:
                self._notifier.incident_pending(row)
            else:
                self._notifier.incident_finished(row)
        except Exception as exc:  # noqa: BLE001 — never lose an incident silently
            logger.exception("workflow failed", extra={"event": "workflow_error", "incident_id": incident_id})
            row = self._incidents.get(incident_id) or {"state": {}}
            state = row["state"]
            state["trace"] = state.get("trace", []) + trace("error", f"Workflow error: {type(exc).__name__}: {exc}",
                                                            status="error")
            self._incidents.save_state(incident_id, state, "ERROR")

    def shutdown(self) -> None:
        self._threads.shutdown(wait=False, cancel_futures=True)
