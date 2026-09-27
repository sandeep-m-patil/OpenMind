"""Node 7 — Controlled Execution: approved runbook ID → Ansible, dry-run first, then apply."""
import json

from app.agents.deps import AgentDeps
from app.agents.state import IncidentState, trace
from app.tools.base import run_tool

BEFORE_WINDOW = "1m"


def _failure(before: dict, check: dict | None, reason: str) -> dict:
    return {
        "metrics_before": before,
        "execution_result": {"is_success": False, "check": check, "apply": None, "error": reason},
        "status": "REMEDIATION_FAILED",
        "outcome": "REMEDIATION_FAILED",
        "trace": trace("execution", f"Execution aborted: {reason}", status="error"),
    }


def make_execution(deps: AgentDeps):
    def execution(state: IncidentState) -> dict:
        action = state["final_action"]
        runbook = deps.catalog.get(action["runbook_id"])
        before = run_tool("get_metrics", lambda: deps.prometheus.snapshot(BEFORE_WINDOW)).data or state.get("metrics", {})
        try:
            check = deps.executor.run(runbook, action["params"], is_check=True).to_dict()
            if not check["is_success"]:
                return _failure(before, check, f"dry run failed (rc={check['return_code']})")
            applied = deps.executor.run(runbook, action["params"], is_check=False).to_dict()
        except (OSError, ValueError) as exc:
            return _failure(before, None, f"{type(exc).__name__}: {exc}")
        report = json.dumps(applied.get("result"), default=str) if applied.get("result") else "(no report)"
        return {
            "metrics_before": before,
            "execution_result": {"is_success": applied["is_success"], "check": check, "apply": applied},
            "status": "VERIFYING" if applied["is_success"] else "REMEDIATION_FAILED",
            "trace": trace("execution",
                           f"{runbook.id} executed via Ansible: dry-run ok, apply "
                           f"{'ok' if applied['is_success'] else 'FAILED'} in {applied['duration_seconds']}s",
                           [f"Dry-run report: {json.dumps(check.get('result'), default=str)}", f"Apply report: {report}"],
                           "ok" if applied["is_success"] else "error"),
        }

    return execution


def route_after_execution(state: IncidentState) -> str:
    return "verification" if state.get("execution_result", {}).get("is_success") else "learning"
